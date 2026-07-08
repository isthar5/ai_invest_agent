package worker

import (
	"context"
	"log"
	"sync"
	"sync/atomic"
	"time"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
	"github.com/ai-invest-agent/go-runtime/internal/event"
	"github.com/ai-invest-agent/go-runtime/internal/executor"
	"github.com/ai-invest-agent/go-runtime/internal/queue"
	"github.com/ai-invest-agent/go-runtime/internal/retry"
)

// CancelRegistry allows the worker to register/unregister running task cancel functions.
// The Scheduler implements this to support CancelTask on running tasks.
type CancelRegistry interface {
	RegisterRunningTask(taskID string, cancel context.CancelFunc)
	UnregisterRunningTask(taskID string)
	IsTaskCancelled(taskID string) bool
}

// Worker executes tasks from a channel with retry, timeout, and cancellation support.
//
// Lifecycle:
//
//	[Start] → Idle → (receives task) → Busy → (task done) → Idle → ...
//	                                                      → Stopped
//
// Thread-safe status transitions via atomic operations.
type Worker struct {
	ID             string
	Status         atomic.Value // WorkerStatus
	CurrentTask    atomic.Value // *pb.Task (current task, nil when idle)
	StartedAt      time.Time
	CompletedCount atomic.Int64
	FailedCount    atomic.Int64

	// Internal dependencies
	taskQueue      *queue.TaskQueue
	results        chan<- *pb.TaskResult
	exec           executor.Executor
	retryPolicy    *retry.Policy
	cancelRegistry CancelRegistry
	emitter        *event.Emitter

	// Lifecycle
	ctx    context.Context
	cancel context.CancelFunc
	wg     *sync.WaitGroup
}

// NewWorker creates a new Worker that dequeues from the TaskQueue.
func NewWorker(
	id string,
	taskQueue *queue.TaskQueue,
	results chan<- *pb.TaskResult,
	exec executor.Executor,
	retryPolicy *retry.Policy,
	cancelRegistry CancelRegistry,
	emitter *event.Emitter,
	wg *sync.WaitGroup,
) *Worker {
	w := &Worker{
		ID:             id,
		taskQueue:      taskQueue,
		results:        results,
		exec:           exec,
		retryPolicy:    retryPolicy,
		cancelRegistry: cancelRegistry,
		emitter:        emitter,
		StartedAt:      time.Now(),
		wg:             wg,
	}
	w.Status.Store(WorkerIdle)
	w.CurrentTask.Store((*pb.Task)(nil))
	return w
}

// Run starts the worker loop. Blocks until the task channel is closed or context cancelled.
func (w *Worker) Run(ctx context.Context) {
	w.ctx = ctx
	log.Printf("[worker-%s] started", w.ID)

	w.emitEvent(event.WorkerStarted, "", map[string]interface{}{
		"worker_id":  w.ID,
		"started_at": w.StartedAt.Format(time.RFC3339),
	})

	for {
		w.Status.Store(WorkerIdle)
		w.CurrentTask.Store((*pb.Task)(nil))
		w.emitEvent(event.WorkerIdle, "", map[string]interface{}{
			"worker_id":       w.ID,
			"completed_count": w.CompletedCount.Load(),
			"failed_count":    w.FailedCount.Load(),
		})

		// Dequeue from TaskQueue (blocks until task available or context cancelled)
		task, err := w.taskQueue.Dequeue(ctx)
		if err != nil {
			// Context cancelled or queue closed
			log.Printf("[worker-%s] dequeue stopped: %v", w.ID, err)
			w.Status.Store(WorkerStopped)
			w.emitEvent(event.WorkerStopped, "", map[string]interface{}{
				"worker_id":       w.ID,
				"completed_count": w.CompletedCount.Load(),
				"failed_count":    w.FailedCount.Load(),
				"reason":          err.Error(),
			})
			return
		}

		w.processTask(ctx, task)
	}
}

// processTask handles a single task with retry, timeout, and cancellation.
func (w *Worker) processTask(parentCtx context.Context, task *pb.Task) {
	w.Status.Store(WorkerBusy)
	w.CurrentTask.Store(task)

	// 1. Check if already cancelled (fast path)
	if w.cancelRegistry.IsTaskCancelled(task.TaskId) {
		w.handleCancelled(task)
		return
	}

	// 2. Apply timeout
	timeout := time.Duration(task.TimeoutMs) * time.Millisecond
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	taskCtx, taskCancel := context.WithTimeout(parentCtx, timeout)

	// 3. Register cancel function so Scheduler can CancelTask on running tasks
	w.cancelRegistry.RegisterRunningTask(task.TaskId, taskCancel)
	defer w.cancelRegistry.UnregisterRunningTask(task.TaskId)

	// 4. Double-check cancellation (between dequeue and register)
	if w.cancelRegistry.IsTaskCancelled(task.TaskId) {
		taskCancel()
		w.handleCancelled(task)
		return
	}

	// 5. Emit TaskStarted
	w.emitEvent(event.TaskStarted, task.TaskId, map[string]interface{}{
		"skill":      task.Skill,
		"timeout_ms": timeout.Milliseconds(),
		"worker_id":  w.ID,
	})

	// 6. Execute with retry
	startTime := time.Now()
	finalResult := w.executeWithRetry(taskCtx, task)
	taskCancel() // release context resources immediately (prevents goroutine leak)

	// 7. Record latency
	finalResult.LatencyMs = float64(time.Since(startTime).Milliseconds())

	// 8. Emit final event and update metrics
	w.emitFinalEvent(finalResult)

	// 9. Send result back (non-blocking, respect parent context)
	select {
	case <-parentCtx.Done():
		log.Printf("[worker-%s] parent context done, dropping result for %s", w.ID, task.TaskId)
	case w.results <- finalResult:
	}
}

// executeWithRetry runs the executor with retry policy.
// Returns the final TaskResult after all retries are exhausted or success.
func (w *Worker) executeWithRetry(ctx context.Context, task *pb.Task) *pb.TaskResult {
	var lastResult *pb.TaskResult

	// Determine retry policy: per-task overrides global
	policy := w.retryPolicy
	if task.MaxRetries > 0 {
		policy = retry.NewPolicy(
			int(task.MaxRetries),
			w.retryPolicy.InitialBackoff,
			w.retryPolicy.MaxBackoff,
			w.retryPolicy.BackoffMultiplier,
		)
	}

	for attempt := 0; ; attempt++ {
		// Check context before each attempt
		select {
		case <-ctx.Done():
			errMsg := ctx.Err().Error()
			status := pb.TaskStatus_TASK_STATUS_FAILED
			if ctx.Err() == context.DeadlineExceeded {
				status = pb.TaskStatus_TASK_STATUS_TIMEOUT
			} else if ctx.Err() == context.Canceled {
				status = pb.TaskStatus_TASK_STATUS_CANCELLED
			}
			return &pb.TaskResult{
				TaskId:     task.TaskId,
				Status:     status,
				Error:      errMsg,
				RetryCount: int32(attempt),
			}
		default:
		}

		// Execute
		result := w.exec.Execute(ctx, task)
		result.RetryCount = int32(attempt)

		// Success
		if result.Status == pb.TaskStatus_TASK_STATUS_COMPLETED {
			w.CompletedCount.Add(1)
			return result
		}

		// Non-retryable statuses: timeout, cancelled — don't retry
		if result.Status == pb.TaskStatus_TASK_STATUS_TIMEOUT ||
			result.Status == pb.TaskStatus_TASK_STATUS_CANCELLED {
			w.FailedCount.Add(1)
			return result
		}

		lastResult = result

		// Should we retry?
		if !policy.ShouldRetry(attempt) {
			w.FailedCount.Add(1)
			return lastResult
		}

		// Emit retry event
		w.emitEvent(event.TaskRetry, task.TaskId, map[string]interface{}{
			"attempt":    attempt + 1,
			"max_retries": policy.MaxRetries,
			"backoff_ms": policy.Backoff(attempt).Milliseconds(),
			"error":      result.Error,
			"worker_id":  w.ID,
		})

		// Backoff
		if err := policy.SleepWithContext(ctx, attempt); err != nil {
			errMsg := err.Error()
			status := pb.TaskStatus_TASK_STATUS_FAILED
			if ctx.Err() == context.DeadlineExceeded {
				status = pb.TaskStatus_TASK_STATUS_TIMEOUT
			} else if ctx.Err() == context.Canceled {
				status = pb.TaskStatus_TASK_STATUS_CANCELLED
			}
			return &pb.TaskResult{
				TaskId:     task.TaskId,
				Status:     status,
				Error:      errMsg,
				RetryCount: int32(attempt + 1),
			}
		}
	}
}

// handleCancelled handles a task that was cancelled before execution started.
func (w *Worker) handleCancelled(task *pb.Task) {
	result := &pb.TaskResult{
		TaskId: task.TaskId,
		Status: pb.TaskStatus_TASK_STATUS_CANCELLED,
		Error:  "task cancelled before execution",
	}
	w.emitEvent(event.TaskCancelled, task.TaskId, map[string]interface{}{
		"reason":    "cancelled_before_execution",
		"worker_id": w.ID,
	})
	// Don't send result — the Scheduler already sent CANCELLED via the pending channel
	_ = result
}

// emitFinalEvent publishes the appropriate completion event based on result status.
func (w *Worker) emitFinalEvent(result *pb.TaskResult) {
	var eventType event.EventType
	data := map[string]interface{}{
		"latency_ms":  result.LatencyMs,
		"retry_count": result.RetryCount,
		"worker_id":   w.ID,
	}

	switch result.Status {
	case pb.TaskStatus_TASK_STATUS_COMPLETED:
		eventType = event.TaskCompleted
	case pb.TaskStatus_TASK_STATUS_TIMEOUT:
		eventType = event.TaskTimeout
		data["error"] = result.Error
	case pb.TaskStatus_TASK_STATUS_CANCELLED:
		eventType = event.TaskCancelled
		data["error"] = result.Error
	default:
		eventType = event.TaskFailed
		data["error"] = result.Error
	}

	w.emitEvent(eventType, result.TaskId, data)
}

// emitEvent is a helper to emit an event safely.
func (w *Worker) emitEvent(eventType event.EventType, taskID string, data map[string]interface{}) {
	if w.emitter == nil {
		return
	}
	w.emitter.Emit(event.NewEvent(eventType, taskID, data))
}

// GetStatus returns the current worker status.
func (w *Worker) GetStatus() WorkerStatus {
	return w.Status.Load().(WorkerStatus)
}

// GetCurrentTask returns the current task being executed, or nil if idle.
func (w *Worker) GetCurrentTask() *pb.Task {
	t := w.CurrentTask.Load()
	if t == nil {
		return nil
	}
	return t.(*pb.Task)
}

// IsIdle returns true if the worker is idle.
func (w *Worker) IsIdle() bool {
	return w.GetStatus() == WorkerIdle
}

// IsBusy returns true if the worker is executing a task.
func (w *Worker) IsBusy() bool {
	return w.GetStatus() == WorkerBusy
}

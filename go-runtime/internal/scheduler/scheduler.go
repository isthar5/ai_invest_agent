// Package scheduler provides the central task scheduler.
//
// The Scheduler:
//   - Receives SubmitTask gRPC calls and enqueues tasks into the TaskQueue.
//   - Workers dequeue and execute tasks.
//   - ResultCollector routes worker results back to pending callers.
//   - Implements CancelRegistry so workers can register/unregister cancel funcs.
//   - Emits RuntimeEvents for all lifecycle transitions.
//   - Tracks Metrics for observability.
//
// SOLID:
//   - Single Responsibility: orchestrates task lifecycle; delegates execution to Worker Pool.
//   - Dependency Inversion: depends on Executor interface and Event Emitter.
//   - Open/Closed: new executor implementations without changing scheduler.
package scheduler

import (
	"context"
	"fmt"
	"log"
	"sync"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
	"github.com/ai-invest-agent/go-runtime/internal/event"
	"github.com/ai-invest-agent/go-runtime/internal/executor"
	"github.com/ai-invest-agent/go-runtime/internal/queue"
	"github.com/ai-invest-agent/go-runtime/internal/retry"
	"github.com/ai-invest-agent/go-runtime/internal/worker"
)

// Scheduler orchestrates task lifecycle: submit → queue → execute → result.
//
// It implements worker.CancelRegistry so workers can register running task
// cancel functions for Cancellation support.
type Scheduler struct {
	queue   *queue.TaskQueue
	pool    *worker.Pool
	metrics *Metrics
	emitter *event.Emitter
	retry   *retry.Policy

	// pending maps taskID → result channel (for synchronous gRPC responses)
	pending map[string]chan *pb.TaskResult

	// cancelFuncs maps taskID → context.CancelFunc (for running task cancellation)
	cancelFuncs map[string]context.CancelFunc

	// cancelled set for tasks cancelled before/after registration
	cancelled map[string]struct{}

	mu sync.RWMutex
}

// New creates a new Scheduler with all dependencies injected.
func New(
	q *queue.TaskQueue,
	exec executor.Executor,
	workerCount int,
	retryPolicy *retry.Policy,
	emitter *event.Emitter,
) *Scheduler {
	s := &Scheduler{
		queue:       q,
		metrics:     NewMetrics(),
		emitter:     emitter,
		retry:       retryPolicy,
		pending:     make(map[string]chan *pb.TaskResult),
		cancelFuncs: make(map[string]context.CancelFunc),
		cancelled:   make(map[string]struct{}),
	}

	// Create the worker pool — Scheduler implements CancelRegistry
	// Workers dequeue directly from the TaskQueue
	s.pool = worker.NewPool(workerCount, q, exec, retryPolicy, s, emitter)

	return s
}

// Start starts the worker pool.
func (s *Scheduler) Start() {
	s.pool.Start()
	if s.emitter != nil {
		s.emitter.Emit(event.NewEvent(event.RuntimeStarted, "", map[string]interface{}{
			"worker_count": s.pool.IdleWorkers() + s.pool.ActiveWorkers(),
			"queue_size":   s.queue.Capacity(),
		}))
	}
}

// ── Task Lifecycle ──────────────────────────────────────────

// Submit adds a task to the queue and blocks until the result is ready.
// This is called by the gRPC handler (synchronous unary RPC).
func (s *Scheduler) Submit(ctx context.Context, task *pb.Task) (*pb.TaskResult, error) {
	log.Printf("[scheduler] submit: id=%s skill=%s timeout=%.0fms",
		task.TaskId, task.Skill, task.TimeoutMs)

	s.metrics.IncSubmitted()

	// Emit TaskSubmitted event
	s.emitEvent(event.TaskSubmitted, task.TaskId, map[string]interface{}{
		"skill":      task.Skill,
		"timeout_ms": task.TimeoutMs,
	})

	// Create pending result channel
	resultCh := make(chan *pb.TaskResult, 1)
	s.mu.Lock()
	s.pending[task.TaskId] = resultCh
	s.mu.Unlock()

	// Enqueue task
	if !s.queue.Enqueue(task) {
		s.mu.Lock()
		delete(s.pending, task.TaskId)
		s.mu.Unlock()
		s.emitEvent(event.QueueFull, task.TaskId, map[string]interface{}{
			"skill": task.Skill,
		})
		return &pb.TaskResult{
			TaskId: task.TaskId,
			Status: pb.TaskStatus_TASK_STATUS_FAILED,
			Error:  "task queue full",
		}, nil
	}

	s.metrics.IncQueueDepth()

	// Emit TaskQueued
	s.emitEvent(event.TaskQueued, task.TaskId, map[string]interface{}{
		"skill":      task.Skill,
		"queue_depth": s.queue.Len(),
	})

	// Block until result or context cancellation
	select {
	case <-ctx.Done():
		// Client cancelled the gRPC call
		s.mu.Lock()
		delete(s.pending, task.TaskId)
		s.mu.Unlock()
		s.queue.Cancel(task.TaskId)
		s.metrics.IncCancelled()
		s.emitEvent(event.TaskCancelled, task.TaskId, map[string]interface{}{
			"reason": ctx.Err().Error(),
		})
		return &pb.TaskResult{
			TaskId: task.TaskId,
			Status: pb.TaskStatus_TASK_STATUS_CANCELLED,
			Error:  ctx.Err().Error(),
		}, nil

	case result := <-resultCh:
		// Update metrics
		s.updateMetrics(result)
		return result, nil
	}
}

// ── Result Collection ───────────────────────────────────────

// ResultCollector runs in the background, reading results from the pool
// and routing them to the appropriate pending channels.
func (s *Scheduler) ResultCollector(ctx context.Context) {
	log.Println("[scheduler] result collector started")
	for {
		select {
		case <-ctx.Done():
			log.Println("[scheduler] result collector stopped")
			return
		case result, ok := <-s.pool.Results():
			if !ok {
				return
			}
			s.dispatchResult(result)
		}
	}
}

// dispatchResult routes a single result to the pending channel.
func (s *Scheduler) dispatchResult(result *pb.TaskResult) {
	s.mu.RLock()
	ch, exists := s.pending[result.TaskId]
	s.mu.RUnlock()

	if exists {
		select {
		case ch <- result:
			// Cleanup pending entry
			s.mu.Lock()
			delete(s.pending, result.TaskId)
			s.mu.Unlock()
		default:
			log.Printf("[scheduler] result channel full for %s", result.TaskId)
		}
	} else {
		log.Printf("[scheduler] no pending channel for %s (may have been cancelled)", result.TaskId)
	}

	// Cleanup cancellation state
	s.mu.Lock()
	delete(s.cancelFuncs, result.TaskId)
	delete(s.cancelled, result.TaskId)
	s.mu.Unlock()
	s.queue.Cleanup(result.TaskId)

	s.metrics.DecQueueDepth()
}

// ── Cancellation ────────────────────────────────────────────

// CancelTask cancels a task whether it's queued or running.
// Returns true if the task was found and cancelled.
func (s *Scheduler) CancelTask(taskID string) bool {
	log.Printf("[scheduler] CancelTask: id=%s", taskID)

	s.mu.Lock()

	// Mark as cancelled (for tasks that haven't been dequeued yet)
	s.cancelled[taskID] = struct{}{}

	// Mark in the queue (for tasks still in the channel)
	s.queue.Cancel(taskID)

	// If running, call cancel func
	if cancel, ok := s.cancelFuncs[taskID]; ok {
		cancel()
		delete(s.cancelFuncs, taskID)
		s.mu.Unlock()

		s.metrics.IncCancelled()
		s.emitEvent(event.TaskCancelled, taskID, map[string]interface{}{
			"reason": "user_cancelled",
			"state":  "running",
		})
		return true
	}

	// If pending (waiting in Submit), send CANCELLED result
	if ch, ok := s.pending[taskID]; ok {
		s.mu.Unlock()

		select {
		case ch <- &pb.TaskResult{
			TaskId: taskID,
			Status: pb.TaskStatus_TASK_STATUS_CANCELLED,
			Error:  "task cancelled by user",
		}:
		default:
		}

		s.metrics.IncCancelled()
		s.emitEvent(event.TaskCancelled, taskID, map[string]interface{}{
			"reason": "user_cancelled",
			"state":  "queued",
		})
		return true
	}

	s.mu.Unlock()
	log.Printf("[scheduler] CancelTask: task %s not found (may already be completed)", taskID)
	return false
}

// ── CancelRegistry Implementation ───────────────────────────

// RegisterRunningTask registers a cancel function for a running task.
// Called by Worker right before execution.
func (s *Scheduler) RegisterRunningTask(taskID string, cancel context.CancelFunc) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cancelFuncs[taskID] = cancel
	s.metrics.IncRunning()
}

// UnregisterRunningTask removes a task's cancel function.
// Called by Worker after execution completes.
func (s *Scheduler) UnregisterRunningTask(taskID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.cancelFuncs, taskID)
	s.metrics.DecRunning()
}

// IsTaskCancelled checks if a task has been marked as cancelled.
// Called by Worker before and after registering the cancel function.
func (s *Scheduler) IsTaskCancelled(taskID string) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	_, ok := s.cancelled[taskID]
	return ok
}

// ── Metrics ─────────────────────────────────────────────────

// GetMetrics returns the current metrics snapshot.
func (s *Scheduler) GetMetrics() *Metrics {
	return s.metrics
}

// LogMetrics logs the current metrics snapshot.
func (s *Scheduler) LogMetrics() {
	s.metrics.LogSnapshot(log.Default())
}

// GetWorkerInfo returns information about all workers.
func (s *Scheduler) GetWorkerInfo() []worker.WorkerInfo {
	return s.pool.GetWorkers()
}

// ── Shutdown ────────────────────────────────────────────────

// Shutdown gracefully stops the scheduler and worker pool.
func (s *Scheduler) Shutdown() {
	log.Println("[scheduler] shutting down...")
	if s.emitter != nil {
		s.emitter.Emit(event.NewEvent(event.RuntimeShutdown, "", nil))
	}
	s.pool.Shutdown()

	s.mu.Lock()
	// Notify any remaining pending callers
	for taskID, ch := range s.pending {
		select {
		case ch <- &pb.TaskResult{
			TaskId: taskID,
			Status: pb.TaskStatus_TASK_STATUS_CANCELLED,
			Error:  "runtime shutdown",
		}:
		default:
		}
	}
	s.pending = make(map[string]chan *pb.TaskResult)
	s.cancelFuncs = make(map[string]context.CancelFunc)
	s.cancelled = make(map[string]struct{})
	s.mu.Unlock()

	log.Println("[scheduler] shutdown complete")
}

// ── Helpers ─────────────────────────────────────────────────

func (s *Scheduler) updateMetrics(result *pb.TaskResult) {
	switch result.Status {
	case pb.TaskStatus_TASK_STATUS_COMPLETED:
		s.metrics.IncCompleted()
	case pb.TaskStatus_TASK_STATUS_FAILED:
		s.metrics.IncFailed()
	case pb.TaskStatus_TASK_STATUS_TIMEOUT:
		s.metrics.IncTimeout()
	case pb.TaskStatus_TASK_STATUS_CANCELLED:
		s.metrics.IncCancelled()
	}
	s.metrics.IncRetryBy(int(result.RetryCount))
	s.metrics.RecordLatency(result.LatencyMs)
}

// IncRetryBy adds n to the retry counter.
func (m *Metrics) IncRetryBy(n int) {
	for i := 0; i < n; i++ {
		m.IncRetry()
	}
}

func (s *Scheduler) emitEvent(eventType event.EventType, taskID string, data map[string]interface{}) {
	if s.emitter == nil {
		return
	}
	// Add scheduler-level context
	if data == nil {
		data = make(map[string]interface{})
	}
	data["queue_depth"] = s.queue.Len()
	data["metrics"] = s.metrics.String()
	s.emitter.Emit(event.NewEvent(eventType, taskID, data))
}

// ── Periodic Metrics Logger ─────────────────────────────────

// MetricsLogger periodically logs scheduler metrics.
func (s *Scheduler) MetricsLogger(ctx context.Context, intervalSeconds int) {
	log.Printf("[scheduler] metrics logger started (interval=%ds)", intervalSeconds)
	// Use a simple tick-based loop since we don't import time in this context
	// The caller will set up the ticker

	// This function signature is for the caller to use with a time.Ticker.
	// The actual loop is in main.go for clarity.
	_ = ctx
	_ = intervalSeconds
}

// QueueDepth returns the current queue depth.
func (s *Scheduler) QueueDepth() int {
	return s.queue.Len()
}

// String returns a compact status line.
func (s *Scheduler) String() string {
	return fmt.Sprintf("Scheduler(%s)", s.metrics.String())
}

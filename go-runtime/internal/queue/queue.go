// Package queue provides a FIFO TaskQueue backed by a buffered channel.
//
// Design:
//   - Uses Go channel for FIFO ordering and blocking dequeue.
//   - Cancelled set (sync.Map) for O(1) cancellation of queued tasks
//     (since channels don't support removal from the middle).
//   - Thread-safe: enqueue, dequeue, cancel can be called concurrently.
//
// Cancellation flow:
//   1. Cancel(taskID) marks the task in the cancelled set.
//   2. Dequeue() skips cancelled tasks automatically.
//   3. The Scheduler is responsible for sending the CANCELLED TaskResult
//      to the pending waiter when Cancel is called.
//
// SOLID: Single Responsibility — only enqueue/dequeue/cancel; no scheduling logic.
package queue

import (
	"context"
	"fmt"
	"sync"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
)

// TaskQueue is a FIFO queue for tasks with cancellation support.
type TaskQueue struct {
	tasks     chan *pb.Task
	cancelled sync.Map   // taskID → struct{} (set of cancelled task IDs)
	maxSize   int
	closed    bool
	mu        sync.Mutex // protects closed flag
}

// New creates a new TaskQueue with the given capacity.
func New(capacity int) *TaskQueue {
	if capacity <= 0 {
		capacity = 256
	}
	return &TaskQueue{
		tasks:   make(chan *pb.Task, capacity),
		maxSize: capacity,
	}
}

// Enqueue adds a task to the queue. Non-blocking.
// Returns true if the task was enqueued, false if the queue is full.
func (q *TaskQueue) Enqueue(task *pb.Task) bool {
	select {
	case q.tasks <- task:
		return true
	default:
		return false // queue full
	}
}

// Dequeue removes and returns the next non-cancelled task from the queue.
// Blocks until a task is available or the context is cancelled.
// Automatically skips tasks that have been cancelled.
// Returns an error if the context is cancelled or the queue is closed.
func (q *TaskQueue) Dequeue(ctx context.Context) (*pb.Task, error) {
	for {
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case task, ok := <-q.tasks:
			if !ok {
				return nil, fmt.Errorf("queue closed")
			}
			// Skip cancelled tasks — they were already handled by Scheduler.CancelTask
			if _, cancelled := q.cancelled.Load(task.TaskId); !cancelled {
				return task, nil
			}
			// Task was cancelled, drop it and continue dequeueing
		}
	}
}

// Cancel marks a task as cancelled.
// If the task is still in the queue, it will be skipped by Dequeue().
// Returns true if the task was newly cancelled, false if already cancelled.
func (q *TaskQueue) Cancel(taskID string) bool {
	_, loaded := q.cancelled.LoadOrStore(taskID, struct{}{})
	return !loaded
}

// IsCancelled checks if a task has been cancelled.
func (q *TaskQueue) IsCancelled(taskID string) bool {
	_, ok := q.cancelled.Load(taskID)
	return ok
}

// Len returns the approximate number of tasks currently in the queue.
// Note: this does NOT subtract cancelled tasks (they're still in the channel).
func (q *TaskQueue) Len() int {
	return len(q.tasks)
}

// Capacity returns the maximum queue size.
func (q *TaskQueue) Capacity() int {
	return q.maxSize
}

// Close closes the queue. No more tasks can be enqueued.
// Workers will drain remaining tasks then exit.
func (q *TaskQueue) Close() {
	q.mu.Lock()
	defer q.mu.Unlock()
	if !q.closed {
		q.closed = true
		close(q.tasks)
	}
}

// Cleanup removes a cancelled task ID from the set (for memory management).
// Called after a cancelled task has been fully handled.
func (q *TaskQueue) Cleanup(taskID string) {
	q.cancelled.Delete(taskID)
}

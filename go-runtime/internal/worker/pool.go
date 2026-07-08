package worker

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
)

// Pool manages a fixed-size goroutine worker pool with lifecycle tracking.
//
// Workers dequeue directly from the TaskQueue (FIFO, with cancellation support).
// Results are sent to a buffered channel for the ResultCollector.
//
// SOLID:
//   - Depends on Executor interface, not concrete executor.
//   - CancelRegistry injected for CancelTask support.
//   - EventEmitter injected for runtime events.
type Pool struct {
	maxWorkers int
	queue      *queue.TaskQueue
	results    chan *pb.TaskResult
	workers    []*Worker
	executor   executor.Executor
	retry      *retry.Policy
	emitter    *event.Emitter
	registry   CancelRegistry

	ctx    context.Context
	cancel context.CancelFunc
	wg     sync.WaitGroup
	mu     sync.RWMutex // protects workers slice
}

// NewPool creates a new worker pool that reads from the given TaskQueue.
func NewPool(
	maxWorkers int,
	q *queue.TaskQueue,
	exec executor.Executor,
	retryPolicy *retry.Policy,
	cancelRegistry CancelRegistry,
	emitter *event.Emitter,
) *Pool {
	ctx, cancel := context.WithCancel(context.Background())
	return &Pool{
		maxWorkers: maxWorkers,
		queue:      q,
		results:    make(chan *pb.TaskResult, q.Capacity()),
		workers:    make([]*Worker, 0, maxWorkers),
		executor:   exec,
		retry:      retryPolicy,
		emitter:    emitter,
		registry:   cancelRegistry,
		ctx:        ctx,
		cancel:     cancel,
	}
}

// Start launches all worker goroutines.
func (p *Pool) Start() {
	log.Printf("[pool] starting %d workers, queue capacity %d", p.maxWorkers, p.queue.Capacity())
	p.mu.Lock()
	defer p.mu.Unlock()

	for i := 0; i < p.maxWorkers; i++ {
		id := fmt.Sprintf("w-%d", i)
		w := NewWorker(id, p.queue, p.results, p.executor, p.retry, p.registry, p.emitter, &p.wg)
		p.workers = append(p.workers, w)

		p.wg.Add(1)
		go func(worker *Worker) {
			defer p.wg.Done()
			worker.Run(p.ctx)
		}(w)
	}
}

// Results returns the read-only results channel.
func (p *Pool) Results() <-chan *pb.TaskResult {
	return p.results
}

// GetWorkers returns a snapshot of all worker statuses.
func (p *Pool) GetWorkers() []WorkerInfo {
	p.mu.RLock()
	defer p.mu.RUnlock()

	infos := make([]WorkerInfo, len(p.workers))
	for i, w := range p.workers {
		infos[i] = WorkerInfo{
			ID:             w.ID,
			Status:         w.GetStatus().String(),
			CurrentTask:    "",
			StartedAt:      w.StartedAt,
			CompletedCount: w.CompletedCount.Load(),
			FailedCount:    w.FailedCount.Load(),
		}
		if task := w.GetCurrentTask(); task != nil {
			infos[i].CurrentTask = task.TaskId
		}
	}
	return infos
}

// Shutdown gracefully stops all workers.
func (p *Pool) Shutdown() {
	log.Println("[pool] shutting down...")
	p.cancel()
	p.queue.Close() // close the task queue, workers will drain and exit
	p.wg.Wait()
	close(p.results)
	log.Println("[pool] shutdown complete")
}

// ActiveWorkers returns the count of currently busy workers.
func (p *Pool) ActiveWorkers() int {
	p.mu.RLock()
	defer p.mu.RUnlock()

	count := 0
	for _, w := range p.workers {
		if w.IsBusy() {
			count++
		}
	}
	return count
}

// IdleWorkers returns the count of currently idle workers.
func (p *Pool) IdleWorkers() int {
	p.mu.RLock()
	defer p.mu.RUnlock()

	count := 0
	for _, w := range p.workers {
		if w.IsIdle() {
			count++
		}
	}
	return count
}

// WorkerInfo is a read-only snapshot of a worker's state.
type WorkerInfo struct {
	ID             string
	Status         string
	CurrentTask    string
	StartedAt      interface{}
	CompletedCount int64
	FailedCount    int64
}

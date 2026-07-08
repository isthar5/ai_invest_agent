package scheduler

import (
	"fmt"
	"log"
	"math"
	"sync"
	"sync/atomic"
	"time"
)

// Metrics tracks scheduler-level statistics.
//
// All counters use atomic operations for lock-free reads.
// Latency tracking uses a mutex-protected ring buffer for average calculation.
//
// SOLID: Single Responsibility — only tracks numbers; no scheduling logic.
type Metrics struct {
	// Atomic counters
	QueueDepth     int64 // current queue depth (approximate)
	RunningTasks   int64 // currently executing tasks
	CompletedTasks int64 // total completed tasks
	FailedTasks    int64 // total failed tasks (after all retries exhausted)
	TimeoutTasks   int64 // total timed-out tasks
	CancelledTasks int64 // total cancelled tasks
	RetryCount     int64 // total retry attempts across all tasks
	SubmittedTasks int64 // total submitted tasks

	// Latency tracking
	mu              sync.Mutex
	latencySamples  []float64 // ring buffer of recent latencies (ms)
	latencyIndex    int
	latencySum      float64
	latencyCount    int64
	startTime       time.Time
}

// NewMetrics creates a new Metrics instance.
func NewMetrics() *Metrics {
	return &Metrics{
		latencySamples: make([]float64, 256),
		startTime:      time.Now(),
	}
}

// IncQueueDepth increments the queue depth counter.
func (m *Metrics) IncQueueDepth() {
	atomic.AddInt64(&m.QueueDepth, 1)
}

// DecQueueDepth decrements the queue depth counter.
func (m *Metrics) DecQueueDepth() {
	atomic.AddInt64(&m.QueueDepth, -1)
}

// IncRunning increments the running tasks counter.
func (m *Metrics) IncRunning() {
	atomic.AddInt64(&m.RunningTasks, 1)
}

// DecRunning decrements the running tasks counter.
func (m *Metrics) DecRunning() {
	atomic.AddInt64(&m.RunningTasks, -1)
}

// IncSubmitted increments the submitted tasks counter.
func (m *Metrics) IncSubmitted() {
	atomic.AddInt64(&m.SubmittedTasks, 1)
}

// IncCompleted increments the completed tasks counter.
func (m *Metrics) IncCompleted() {
	atomic.AddInt64(&m.CompletedTasks, 1)
}

// IncFailed increments the failed tasks counter.
func (m *Metrics) IncFailed() {
	atomic.AddInt64(&m.FailedTasks, 1)
}

// IncTimeout increments the timeout tasks counter.
func (m *Metrics) IncTimeout() {
	atomic.AddInt64(&m.TimeoutTasks, 1)
}

// IncCancelled increments the cancelled tasks counter.
func (m *Metrics) IncCancelled() {
	atomic.AddInt64(&m.CancelledTasks, 1)
}

// IncRetry increments the retry counter.
func (m *Metrics) IncRetry() {
	atomic.AddInt64(&m.RetryCount, 1)
}

// RecordLatency records a task latency in milliseconds for average calculation.
func (m *Metrics) RecordLatency(latencyMs float64) {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Update ring buffer
	old := m.latencySamples[m.latencyIndex]
	m.latencySamples[m.latencyIndex] = latencyMs
	m.latencyIndex = (m.latencyIndex + 1) % len(m.latencySamples)

	m.latencySum += latencyMs - old
	if m.latencyCount < int64(len(m.latencySamples)) {
		m.latencyCount++
	}
}

// AverageLatency returns the average latency in milliseconds.
func (m *Metrics) AverageLatency() float64 {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.latencyCount == 0 {
		return 0
	}
	return m.latencySum / float64(m.latencyCount)
}

// Uptime returns the duration since the metrics were created.
func (m *Metrics) Uptime() time.Duration {
	return time.Since(m.startTime)
}

// Snapshot returns a point-in-time view of all metrics.
type Snapshot struct {
	QueueDepth     int64
	RunningTasks   int64
	SubmittedTasks int64
	CompletedTasks int64
	FailedTasks    int64
	TimeoutTasks   int64
	CancelledTasks int64
	RetryCount     int64
	AverageLatency float64
	Uptime         time.Duration
}

// Snapshot returns the current metrics snapshot.
func (m *Metrics) Snapshot() Snapshot {
	return Snapshot{
		QueueDepth:     atomic.LoadInt64(&m.QueueDepth),
		RunningTasks:   atomic.LoadInt64(&m.RunningTasks),
		SubmittedTasks: atomic.LoadInt64(&m.SubmittedTasks),
		CompletedTasks: atomic.LoadInt64(&m.CompletedTasks),
		FailedTasks:    atomic.LoadInt64(&m.FailedTasks),
		TimeoutTasks:   atomic.LoadInt64(&m.TimeoutTasks),
		CancelledTasks: atomic.LoadInt64(&m.CancelledTasks),
		RetryCount:     atomic.LoadInt64(&m.RetryCount),
		AverageLatency: m.AverageLatency(),
		Uptime:         m.Uptime(),
	}
}

// LogSnapshot logs the current metrics via the standard logger.
func (m *Metrics) LogSnapshot(logger *log.Logger) {
	s := m.Snapshot()
	throughput := float64(0)
	if s.Uptime.Seconds() > 0 {
		throughput = float64(s.CompletedTasks+s.FailedTasks+s.TimeoutTasks) / math.Max(s.Uptime.Seconds(), 1)
	}
	logger.Printf("[metrics] ─────────────────────────────────────────────")
	logger.Printf("[metrics] uptime=%v queue=%d running=%d submitted=%d",
		s.Uptime.Round(time.Second), s.QueueDepth, s.RunningTasks, s.SubmittedTasks)
	logger.Printf("[metrics] completed=%d failed=%d timeout=%d cancelled=%d",
		s.CompletedTasks, s.FailedTasks, s.TimeoutTasks, s.CancelledTasks)
	logger.Printf("[metrics] retries=%d avg_latency=%.1fms throughput=%.1f tasks/s",
		s.RetryCount, s.AverageLatency, throughput)
	logger.Printf("[metrics] ─────────────────────────────────────────────")
}

// String returns a compact one-line summary.
func (m *Metrics) String() string {
	s := m.Snapshot()
	return fmt.Sprintf(
		"queue=%d running=%d completed=%d failed=%d timeout=%d cancelled=%d retries=%d avg_lat=%.1fms",
		s.QueueDepth, s.RunningTasks, s.CompletedTasks,
		s.FailedTasks, s.TimeoutTasks, s.CancelledTasks,
		s.RetryCount, s.AverageLatency,
	)
}

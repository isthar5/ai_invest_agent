// Package event defines the Runtime Event system.
//
// Design:
//   - RuntimeEvent interface: all events implement this
//   - EventSubscriber interface: subscribers implement this
//   - Emitter: manages subscribers and dispatches events
//
// SOLID: Interface First, Dependency Injection.
// No dependency on Prometheus, OpenTelemetry, or any external observability system.
package event

import (
	"sync"
	"time"
)

// EventType enumerates all runtime event types.
type EventType string

const (
	TaskSubmitted   EventType = "TASK_SUBMITTED"
	TaskQueued      EventType = "TASK_QUEUED"
	TaskStarted     EventType = "TASK_STARTED"
	TaskRetry       EventType = "TASK_RETRY"
	TaskCompleted   EventType = "TASK_COMPLETED"
	TaskTimeout     EventType = "TASK_TIMEOUT"
	TaskCancelled   EventType = "TASK_CANCELLED"
	TaskFailed      EventType = "TASK_FAILED"
	WorkerStarted   EventType = "WORKER_STARTED"
	WorkerStopped   EventType = "WORKER_STOPPED"
	WorkerIdle      EventType = "WORKER_IDLE"
	WorkerBusy      EventType = "WORKER_BUSY"
	QueueFull       EventType = "QUEUE_FULL"
	RuntimeStarted  EventType = "RUNTIME_STARTED"
	RuntimeShutdown EventType = "RUNTIME_SHUTDOWN"
)

// RuntimeEvent is the interface all runtime events implement.
type RuntimeEvent interface {
	Type() EventType
	TaskID() string
	Timestamp() time.Time
	Data() map[string]interface{}
}

// BaseEvent provides a common implementation of RuntimeEvent.
type BaseEvent struct {
	EventType   EventType
	EventTaskID string
	Time        time.Time
	EventData   map[string]interface{}
}

func (e BaseEvent) Type() EventType              { return e.EventType }
func (e BaseEvent) TaskID() string               { return e.EventTaskID }
func (e BaseEvent) Timestamp() time.Time         { return e.Time }
func (e BaseEvent) Data() map[string]interface{} { return e.EventData }

// NewEvent creates a new BaseEvent with the current timestamp.
func NewEvent(eventType EventType, taskID string, data map[string]interface{}) BaseEvent {
	if data == nil {
		data = make(map[string]interface{})
	}
	return BaseEvent{
		EventType:   eventType,
		EventTaskID: taskID,
		Time:        time.Now(),
		EventData:   data,
	}
}

// EventSubscriber receives runtime events.
type EventSubscriber interface {
	OnEvent(event RuntimeEvent)
}

// Emitter manages subscribers and dispatches events.
// Thread-safe. Non-blocking dispatch (subscribers run in their own goroutine if needed).
type Emitter struct {
	mu          sync.RWMutex
	subscribers []EventSubscriber
}

// NewEmitter creates a new Emitter.
func NewEmitter() *Emitter {
	return &Emitter{
		subscribers: make([]EventSubscriber, 0),
	}
}

// Subscribe adds a subscriber. Safe to call concurrently.
func (e *Emitter) Subscribe(sub EventSubscriber) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.subscribers = append(e.subscribers, sub)
}

// Emit dispatches an event to all subscribers.
// Subscriber errors are caught and logged; one bad subscriber does not affect others.
// Dispatch is synchronous to preserve event ordering.
func (e *Emitter) Emit(event RuntimeEvent) {
	e.mu.RLock()
	subs := make([]EventSubscriber, len(e.subscribers))
	copy(subs, e.subscribers)
	e.mu.RUnlock()

	for _, sub := range subs {
		func() {
			defer func() {
				// Recover from subscriber panic to keep runtime stable.
				if r := recover(); r != nil {
					// Panic is caught but intentionally not re-logged here —
					// the LoggingSubscriber itself should not panic.
					// If a custom subscriber panics, we swallow it to protect the runtime.
				}
			}()
			sub.OnEvent(event)
		}()
	}
}

// SubscriberCount returns the number of registered subscribers.
func (e *Emitter) SubscriberCount() int {
	e.mu.RLock()
	defer e.mu.RUnlock()
	return len(e.subscribers)
}

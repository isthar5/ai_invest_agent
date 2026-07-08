package worker

import "fmt"

// WorkerStatus represents the current state of a worker.
type WorkerStatus int

const (
	WorkerIdle    WorkerStatus = iota // waiting for task
	WorkerBusy                        // executing a task
	WorkerStopped                     // permanently stopped
)

// String returns a human-readable status name.
func (s WorkerStatus) String() string {
	switch s {
	case WorkerIdle:
		return "IDLE"
	case WorkerBusy:
		return "BUSY"
	case WorkerStopped:
		return "STOPPED"
	default:
		return fmt.Sprintf("UNKNOWN(%d)", s)
	}
}

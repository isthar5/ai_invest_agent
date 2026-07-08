package executor

import (
	"context"
	"encoding/json"
	"math/rand"
	"os"
	"strconv"
	"time"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
)

// MockExecutor simulates skill execution with configurable behavior.
//
// Environment variables (for testing):
//
//	MOCK_FAILURE_RATE=0.0-1.0   — probability of failure (default 0.0)
//	MOCK_MIN_LATENCY_MS=50      — minimum simulated latency (default 50)
//	MOCK_MAX_LATENCY_MS=150     — maximum simulated latency (default 150)
//
// Phase 1-4: mock execution with random sleep.
// Phase 5+: replaced by real SkillExecutor.
type MockExecutor struct {
	failureRate  float64
	minLatencyMs int
	maxLatencyMs int
}

// Ensure MockExecutor implements Executor interface.
var _ Executor = (*MockExecutor)(nil)

// NewMockExecutor creates a new MockExecutor with settings from environment.
func NewMockExecutor() *MockExecutor {
	return &MockExecutor{
		failureRate:  getEnvFloat("MOCK_FAILURE_RATE", 0.0),
		minLatencyMs: getEnvInt("MOCK_MIN_LATENCY_MS", 50),
		maxLatencyMs: getEnvInt("MOCK_MAX_LATENCY_MS", 150),
	}
}

// Execute simulates skill execution.
// Respects context cancellation/timeout.
// May return FAILED based on configured failure rate (for testing retry).
func (e *MockExecutor) Execute(ctx context.Context, task *pb.Task) *pb.TaskResult {
	// Validate task
	if task.TaskId == "" || task.Skill == "" {
		return &pb.TaskResult{
			TaskId: task.TaskId,
			Status: pb.TaskStatus_TASK_STATUS_FAILED,
			Error:  "invalid task: task_id and skill are required",
		}
	}

	// Simulate execution latency
	sleepMs := e.minLatencyMs + rand.Intn(e.maxLatencyMs-e.minLatencyMs+1)
	timer := time.NewTimer(time.Duration(sleepMs) * time.Millisecond)

	select {
	case <-ctx.Done():
		timer.Stop()
		errMsg := ctx.Err().Error()
		status := pb.TaskStatus_TASK_STATUS_FAILED
		if ctx.Err() == context.DeadlineExceeded {
			status = pb.TaskStatus_TASK_STATUS_TIMEOUT
		} else {
			status = pb.TaskStatus_TASK_STATUS_CANCELLED
		}
		return &pb.TaskResult{
			TaskId: task.TaskId,
			Status: status,
			Error:  errMsg,
		}
	case <-timer.C:
		// Normal completion — check for simulated failure
	}

	// Simulate random failure for retry testing
	if e.failureRate > 0 && rand.Float64() < e.failureRate {
		return &pb.TaskResult{
			TaskId: task.TaskId,
			Status: pb.TaskStatus_TASK_STATUS_FAILED,
			Error:  "simulated random failure (MOCK_FAILURE_RATE=" + formatFloat(e.failureRate) + ")",
		}
	}

	// Build mock result
	mockPayload, _ := json.Marshal(map[string]interface{}{
		"mock":         true,
		"skill":        task.Skill,
		"executed_at":  time.Now().UTC().Format(time.RFC3339),
		"simulated_ms": sleepMs,
	})

	return &pb.TaskResult{
		TaskId: task.TaskId,
		Status: pb.TaskStatus_TASK_STATUS_COMPLETED,
		Result: mockPayload,
	}
}

func getEnvFloat(key string, defaultVal float64) float64 {
	if val := os.Getenv(key); val != "" {
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}

func formatFloat(f float64) string {
	return strconv.FormatFloat(f, 'f', 2, 64)
}

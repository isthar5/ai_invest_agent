// Package executor defines the Executor interface and provides a MockExecutor.
//
// SOLID:
//   - Interface Segregation: Executor only has Execute(ctx, task) → TaskResult
//   - Dependency Inversion: Worker depends on Executor interface, not concrete type
//   - Open/Closed: new executor implementations (real skill, HTTP, etc.) without changing Worker
package executor

import (
	"context"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
)

// Executor executes a task and returns a TaskResult.
// Implementations:
//   - MockExecutor: simulates execution with random sleep (Phase 1-4)
//   - SkillExecutor: calls real Python skills via callback (Phase 5+)
//   - HTTPExecutor: calls external HTTP services (future)
type Executor interface {
	Execute(ctx context.Context, task *pb.Task) *pb.TaskResult
}

// Package retry provides RetryPolicy for task execution retry with exponential backoff.
//
// Design:
//   - Pure logic, no side effects, no dependencies on other runtime packages.
//   - RetryPolicy is configured per-task (via protobuf) or globally (via config).
//   - Worker applies RetryPolicy after executor failure.
//
// SOLID: Single Responsibility — only decides "should retry" and "how long to wait".
package retry

import (
	"context"
	"math"
	"time"
)

// Policy defines when and how to retry a failed task.
type Policy struct {
	MaxRetries        int           // Maximum number of retry attempts (0 = no retries)
	InitialBackoff    time.Duration // Initial backoff duration
	MaxBackoff        time.Duration // Maximum backoff cap
	BackoffMultiplier float64       // Exponential multiplier (typically 2.0)
}

// DefaultPolicy returns the standard retry policy.
// max_retries=3, initial_backoff=500ms, multiplier=2.0, max_backoff=10s
func DefaultPolicy() *Policy {
	return &Policy{
		MaxRetries:        3,
		InitialBackoff:    500 * time.Millisecond,
		MaxBackoff:        10 * time.Second,
		BackoffMultiplier: 2.0,
	}
}

// NewPolicy creates a policy from the given parameters.
// Zero values are replaced with defaults.
func NewPolicy(maxRetries int, initialBackoff, maxBackoff time.Duration, multiplier float64) *Policy {
	if maxRetries <= 0 {
		maxRetries = 3
	}
	if initialBackoff <= 0 {
		initialBackoff = 500 * time.Millisecond
	}
	if maxBackoff <= 0 {
		maxBackoff = 10 * time.Second
	}
	if multiplier <= 1.0 {
		multiplier = 2.0
	}
	return &Policy{
		MaxRetries:        maxRetries,
		InitialBackoff:    initialBackoff,
		MaxBackoff:        maxBackoff,
		BackoffMultiplier: multiplier,
	}
}

// ShouldRetry returns true if the given attempt should be retried.
// attempt is 0-indexed (0 = first retry after initial failure).
func (p *Policy) ShouldRetry(attempt int) bool {
	return attempt < p.MaxRetries
}

// Backoff returns the backoff duration for the given attempt.
// Uses exponential backoff: initial * multiplier^attempt, capped at max.
func (p *Policy) Backoff(attempt int) time.Duration {
	if attempt < 0 {
		attempt = 0
	}
	delay := float64(p.InitialBackoff) * math.Pow(p.BackoffMultiplier, float64(attempt))
	d := time.Duration(delay)
	if d > p.MaxBackoff {
		d = p.MaxBackoff
	}
	return d
}

// SleepWithContext sleeps for the given backoff duration, respecting context cancellation.
// Returns nil if sleep completed, or ctx.Err() if context was cancelled.
func (p *Policy) SleepWithContext(ctx context.Context, attempt int) error {
	delay := p.Backoff(attempt)
	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// Executor is a function that can be retried.
// It takes a context and returns an error if execution failed.
type Executor func(ctx context.Context) error

// Execute runs the executor with retry logic.
// Returns the last error if all attempts are exhausted.
// Returns ctx.Err() if context is cancelled during backoff.
//
// Usage:
//
//	err := policy.Execute(ctx, func(ctx context.Context) error {
//	    return executor.Execute(ctx, task)
//	})
func (p *Policy) Execute(ctx context.Context, exec Executor) (lastErr error) {
	for attempt := 0; ; attempt++ {
		// Check context before executing
		select {
		case <-ctx.Done():
			if lastErr == nil {
				return ctx.Err()
			}
			return lastErr
		default:
		}

		// Execute
		err := exec(ctx)
		if err == nil {
			return nil
		}

		// Check if context error (timeout/cancellation) — don't retry these
		if ctx.Err() != nil {
			return err
		}

		lastErr = err

		// Check if we should retry
		if !p.ShouldRetry(attempt) {
			return lastErr
		}

		// Backoff
		if sleepErr := p.SleepWithContext(ctx, attempt); sleepErr != nil {
			return sleepErr
		}
	}
}

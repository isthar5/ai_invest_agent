package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ai-invest-agent/go-runtime/internal/config"
	"github.com/ai-invest-agent/go-runtime/internal/event"
	"github.com/ai-invest-agent/go-runtime/internal/executor"
	grpcserver "github.com/ai-invest-agent/go-runtime/internal/grpc"
	"github.com/ai-invest-agent/go-runtime/internal/queue"
	"github.com/ai-invest-agent/go-runtime/internal/retry"
	"github.com/ai-invest-agent/go-runtime/internal/scheduler"
)

func main() {
	cfg := config.Load()

	log.Printf("=== Go Runtime v0.2 (Feature Complete) ===")
	log.Printf("gRPC port:           %d", cfg.GRPCPort)
	log.Printf("Workers:             %d", cfg.MaxWorkers)
	log.Printf("Queue size:          %d", cfg.QueueSize)
	log.Printf("Max retries:         %d", cfg.MaxRetries)
	log.Printf("Initial backoff:     %dms", cfg.InitialBackoffMs)
	log.Printf("Max backoff:         %dms", cfg.MaxBackoffMs)
	log.Printf("Default timeout:     %dms", cfg.DefaultTimeoutMs)
	log.Printf("Metrics interval:    %ds", cfg.MetricsLogIntervalSec)

	// ── 1. Create Event Emitter + Logging Subscriber ─────
	emitter := event.NewEmitter()
	loggingSub := event.NewLoggingSubscriber(nil) // uses default logger
	emitter.Subscribe(loggingSub)
	log.Printf("[main] event emitter ready (%d subscribers)", emitter.SubscriberCount())

	// ── 2. Create Executor (Mock for Phase 4.2) ──────────
	exec := executor.NewMockExecutor()

	// ── 3. Create RetryPolicy ────────────────────────────
	retryPolicy := retry.NewPolicy(
		cfg.MaxRetries,
		cfg.RetryInitialBackoff(),
		cfg.RetryMaxBackoff(),
		cfg.BackoffMultiplier,
	)

	// ── 4. Create TaskQueue ──────────────────────────────
	q := queue.New(cfg.QueueSize)

	// ── 5. Create Scheduler (with all dependencies) ──────
	sched := scheduler.New(q, exec, cfg.MaxWorkers, retryPolicy, emitter)
	sched.Start()

	// ── 6. Start ResultCollector ─────────────────────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go sched.ResultCollector(ctx)

	// ── 7. Start Metrics Logger ──────────────────────────
	go runMetricsLogger(ctx, sched, cfg.MetricsLogIntervalSec)

	// ── 8. Create gRPC Server ────────────────────────────
	grpcSrv := grpcserver.New(sched)

	// ── 9. Handle Shutdown Signals ───────────────────────
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		port := fmt.Sprintf("%d", cfg.GRPCPort)
		if err := grpcSrv.Start(port); err != nil {
			log.Fatalf("[main] gRPC server failed: %v", err)
		}
	}()

	log.Println("[main] Go Runtime ready. Waiting for tasks...")
	log.Println("[main] Features: TaskQueue | Retry | Timeout | Cancellation | Events | Metrics")

	// ── 10. Wait for Signal ──────────────────────────────
	sig := <-sigCh
	log.Printf("[main] received signal %v, shutting down...", sig)

	grpcSrv.Stop()
	cancel()
	sched.Shutdown()
	log.Println("[main] Go Runtime stopped.")
}

// runMetricsLogger periodically logs scheduler metrics.
func runMetricsLogger(ctx context.Context, sched *scheduler.Scheduler, intervalSec int) {
	if intervalSec <= 0 {
		return
	}
	ticker := time.NewTicker(time.Duration(intervalSec) * time.Second)
	defer ticker.Stop()

	// Log immediately on startup
	sched.LogMetrics()

	for {
		select {
		case <-ctx.Done():
			log.Println("[metrics] logger stopped")
			// Final snapshot
			sched.LogMetrics()
			return
		case <-ticker.C:
			sched.LogMetrics()
			// Also log worker status periodically
			for _, wi := range sched.GetWorkerInfo() {
				log.Printf("[worker] %s status=%s task=%s completed=%d failed=%d",
					wi.ID, wi.Status, wi.CurrentTask, wi.CompletedCount, wi.FailedCount)
			}
		}
	}
}

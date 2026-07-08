package config

import (
	"os"
	"strconv"
	"time"
)

// Config holds all runtime configuration, loaded from environment variables.
type Config struct {
	// gRPC
	GRPCPort int

	// Worker Pool
	MaxWorkers int
	QueueSize  int

	// Retry Policy
	MaxRetries        int
	InitialBackoffMs  int
	MaxBackoffMs      int
	BackoffMultiplier float64

	// Task Timeout
	DefaultTimeoutMs int

	// Metrics
	MetricsLogIntervalSec int
}

// Load reads configuration from environment variables with sensible defaults.
func Load() *Config {
	return &Config{
		GRPCPort:              getEnvInt("GRPC_PORT", 9090),
		MaxWorkers:            getEnvInt("MAX_WORKERS", 8),
		QueueSize:             getEnvInt("QUEUE_SIZE", 256),
		MaxRetries:            getEnvInt("MAX_RETRIES", 3),
		InitialBackoffMs:      getEnvInt("INITIAL_BACKOFF_MS", 500),
		MaxBackoffMs:          getEnvInt("MAX_BACKOFF_MS", 10000),
		BackoffMultiplier:     getEnvFloat("BACKOFF_MULTIPLIER", 2.0),
		DefaultTimeoutMs:      getEnvInt("DEFAULT_TIMEOUT_MS", 30000),
		MetricsLogIntervalSec: getEnvInt("METRICS_LOG_INTERVAL_SEC", 30),
	}
}

// RetryInitialBackoff returns the initial backoff as a time.Duration.
func (c *Config) RetryInitialBackoff() time.Duration {
	return time.Duration(c.InitialBackoffMs) * time.Millisecond
}

// RetryMaxBackoff returns the max backoff as a time.Duration.
func (c *Config) RetryMaxBackoff() time.Duration {
	return time.Duration(c.MaxBackoffMs) * time.Millisecond
}

// DefaultTimeout returns the default task timeout as a time.Duration.
func (c *Config) DefaultTimeout() time.Duration {
	return time.Duration(c.DefaultTimeoutMs) * time.Millisecond
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}

func getEnvFloat(key string, defaultVal float64) float64 {
	if val := os.Getenv(key); val != "" {
		if f, err := strconv.ParseFloat(val, 64); err == nil {
			return f
		}
	}
	return defaultVal
}

package event

import (
	"fmt"
	"log"
	"strings"
	"time"
)

// LoggingSubscriber logs all runtime events using the standard log package.
// This is the minimum viable subscriber — later phases can add
// Prometheus, OpenTelemetry, or other subscribers without changing the event system.
type LoggingSubscriber struct {
	logger *log.Logger
}

// NewLoggingSubscriber creates a subscriber that logs to the default logger.
func NewLoggingSubscriber(logger *log.Logger) *LoggingSubscriber {
	if logger == nil {
		logger = log.Default()
	}
	return &LoggingSubscriber{logger: logger}
}

// OnEvent logs the event in a structured, readable format.
func (s *LoggingSubscriber) OnEvent(event RuntimeEvent) {
	var sb strings.Builder
	sb.WriteString(fmt.Sprintf("[event] %-20s", event.Type()))

	if event.TaskID() != "" {
		sb.WriteString(fmt.Sprintf(" task=%s", event.TaskID()))
	}

	// Format timestamp compactly
	sb.WriteString(fmt.Sprintf(" ts=%s", event.Timestamp().Format(time.RFC3339Nano)))

	// Append data fields
	data := event.Data()
	if len(data) > 0 {
		sb.WriteString(" |")
		for k, v := range data {
			// Skip verbose fields
			if k == "payload" || k == "result" {
				continue
			}
			sb.WriteString(fmt.Sprintf(" %s=%v", k, v))
		}
	}

	s.logger.Println(sb.String())
}

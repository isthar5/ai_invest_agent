package tools

import (
	"fmt"
	"go-agent/schema"
	"strconv"
)

type MathTool struct{}

func (m MathTool) Name() string {
	return "math"
}

func (m MathTool) Schema() schema.ToolSchema {
	return schema.ToolSchema{
		Name:        "math",
		Description: "add two numbers",
		Params: map[string]string{
			"a": "float",
			"b": "float",
		},
	}
}

func toFloat64(v interface{}) (float64, error) {
	switch val := v.(type) {
	case float64:
		return val, nil
	case int:
		return float64(val), nil
	case int64:
		return float64(val), nil
	case string:
		return strconv.ParseFloat(val, 64)
	}
	return 0, fmt.Errorf("invalid number: %v", v)
}

func (m MathTool) Run(input map[string]interface{}) (interface{}, error) {
	a, err := toFloat64(input["a"])
	if err != nil {
		return nil, fmt.Errorf("param 'a': %w", err)
	}
	b, err := toFloat64(input["b"])
	if err != nil {
		return nil, fmt.Errorf("param 'b': %w", err)
	}

	return map[string]interface{}{
		"result": a + b,
	}, nil
}
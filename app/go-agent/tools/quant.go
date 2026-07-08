package tools

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go-agent/schema"
	"net/http"
)

type QuantTool struct {
	Endpoint string
}

func (q QuantTool) Name() string {
	return "quant_analysis"
}

func (q QuantTool) Schema() schema.ToolSchema {
	return schema.ToolSchema{
		Name:        "quant_analysis",
		Description: "quant model",
		Params: map[string]string{
			"stock": "string",
		},
	}
}

func (q QuantTool) Run(input map[string]interface{}) (interface{}, error) {
	body, _ := json.Marshal(input)

	resp, err := httpClient.Post(q.Endpoint, "application/json", bytes.NewBuffer(body))
	if err != nil {
		return nil, fmt.Errorf("quant error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("quant status: %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("quant decode error: %w", err)
	}

	return result, nil
}

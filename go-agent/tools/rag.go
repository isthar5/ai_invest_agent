package tools

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go-agent/schema"
	"net/http"
	"time"
)

var httpClient = &http.Client{
	Timeout: 10 * time.Second,
}

type RAGTool struct {
	Endpoint string
}

func (r RAGTool) Name() string {
	return "rag_search"
}

func (r RAGTool) Schema() schema.ToolSchema {
	return schema.ToolSchema{
		Name:        "rag_search",
		Description: "search via RAG",
		Params: map[string]string{
			"query": "string",
		},
	}
}

func (r RAGTool) Run(input map[string]interface{}) (interface{}, error) {
	// 参数校验
	if query, ok := input["query"]; !ok || query == "" {
		return nil, fmt.Errorf("missing query param")
	}

	body, _ := json.Marshal(input)

	resp, err := httpClient.Post(r.Endpoint, "application/json", bytes.NewBuffer(body))
	if err != nil {
		return nil, fmt.Errorf("rag error: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("rag status: %d", resp.StatusCode)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("rag decode error: %w", err)
	}

	return result, nil
}
package tools

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go-agent/schema"
	"net/http"
	"time"
)

type Text2SQLTool struct {
	Endpoint string
	// 可选：允许的表白名单（可配置）
	AllowedTables []string
	// 可选：最大重试次数
	MaxRetries int
}

func (t Text2SQLTool) Name() string {
	return "text2sql"
}

func (t Text2SQLTool) Schema() schema.ToolSchema {
	return schema.ToolSchema{
		Name:        "text2sql",
		Description: "query structured financial data via natural language",
		Params: map[string]string{
			"query":          "string",
			"user":           "string",
			"allowed_tables": "array (optional)",
		},
	}
}

// Run 执行 Text-to-SQL 查询，包含完整的参数校验、错误处理和重试逻辑
func (t Text2SQLTool) Run(input map[string]interface{}) (interface{}, error) {
	// 1. 校验必填参数
	query, ok := input["query"].(string)
	if !ok || query == "" {
		return nil, fmt.Errorf("param 'query' is required and must be a non-empty string")
	}

	username, ok := input["user"].(string)
	if !ok || username == "" {
		return nil, fmt.Errorf("param 'user' is required and must be a non-empty string")
	}

	// 2. 处理允许的表（优先使用传入的，否则用默认）
	allowedTables := t.AllowedTables
	if len(allowedTables) == 0 {
		allowedTables = []string{"financials", "orders", "balance_sheet"} // 默认白名单
	}
	if tablesParam, exists := input["allowed_tables"]; exists {
		if tables, ok := tablesParam.([]interface{}); ok {
			allowedTables = make([]string, 0, len(tables))
			for _, tbl := range tables {
				if s, ok := tbl.(string); ok {
					allowedTables = append(allowedTables, s)
				}
			}
		}
	}

	// 3. 构造请求体
	reqBody := map[string]interface{}{
		"query_text": query,
		"user": map[string]interface{}{
			"username":       username,
			"allowed_tables": allowedTables,
		},
	}

	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal request: %w", err)
	}

	// 4. 执行请求（支持重试）
	maxRetries := t.MaxRetries
	if maxRetries <= 0 {
		maxRetries = 1 // 默认不重试
	}

	var lastErr error
	for attempt := 0; attempt < maxRetries; attempt++ {
		result, err := t.doRequest(body)
		if err == nil {
			return result, nil
		}
		lastErr = err
		if attempt < maxRetries-1 {
			// 指数退避重试
			time.Sleep(time.Duration(attempt+1) * 500 * time.Millisecond)
		}
	}
	return nil, fmt.Errorf("text2sql failed after %d attempts: %w", maxRetries, lastErr)
}

// doRequest 执行单次 HTTP 请求
func (t Text2SQLTool) doRequest(body []byte) (interface{}, error) {
	resp, err := httpClient.Post(t.Endpoint+"/text2sql", "application/json", bytes.NewBuffer(body))
	if err != nil {
		return nil, fmt.Errorf("text2sql service unreachable: %w", err)
	}
	defer resp.Body.Close()

	// 非 200 状态码时，尝试解析错误详情
	if resp.StatusCode != http.StatusOK {
		var errResp map[string]interface{}
		// 即使解析失败也返回状态码信息
		_ = json.NewDecoder(resp.Body).Decode(&errResp)
		return nil, fmt.Errorf("text2sql returned %d: %v", resp.StatusCode, errResp)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode text2sql response: %w", err)
	}

	return result, nil
}

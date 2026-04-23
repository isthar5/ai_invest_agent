package tools

import (
	"net/http"
	"time"
)

// httpClient 是 tools 包共享的 HTTP 客户端，配置了合理的超时和连接池
var httpClient = &http.Client{
	Timeout: 15 * time.Second,
	Transport: &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 10,
		IdleConnTimeout:     90 * time.Second,
	},
}

package server

import (
	"github.com/gin-gonic/gin"
	"go-agent/router"
	"log"
	"time"
)

type Request struct {
	Tool   string                 `json:"tool"`
	Params map[string]interface{} `json:"params"`
}

type Response struct {
	Success bool        `json:"success"`
	Data    interface{} `json:"data,omitempty"`
	Error   string      `json:"error,omitempty"`
}

func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		c.Next()
		log.Printf("[%s] %s %d %v",
			c.Request.Method,
			c.Request.URL.Path,
			c.Writer.Status(),
			time.Since(start))
	}
}

// SetupRouter 注册所有路由并返回 *gin.Engine，由调用方负责启动
func SetupRouter(r *router.Router) *gin.Engine {
	engine := gin.Default()
	engine.Use(Logger())
	// engine.MaxMultipartMemory = 1 << 20 // 限制请求体 1MB (可选)

	engine.GET("/health", func(c *gin.Context) {
		c.JSON(200, gin.H{"status": "ok"})
	})

	engine.GET("/tools", func(c *gin.Context) {
		c.JSON(200, r.ListTools())
	})

	engine.POST("/call", func(c *gin.Context) {
		var req Request
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(400, Response{Success: false, Error: err.Error()})
			return
		}

		result, err := r.Call(req.Tool, req.Params)
		if err != nil {
			c.JSON(500, Response{Success: false, Error: err.Error()})
			return
		}

		c.JSON(200, Response{Success: true, Data: result})
	})

	return engine
}
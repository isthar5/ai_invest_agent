package main

import (
	"context"
	"go-agent/config"
	"go-agent/router"
	"go-agent/server"
	"go-agent/tools"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	cfg := config.Load()

	r := router.NewRouter()
	r.Register(tools.MathTool{})
	r.Register(tools.RAGTool{Endpoint: cfg.RAGEndpoint})
	r.Register(tools.QuantTool{Endpoint: cfg.QuantEndpoint})
	r.Register(tools.Text2SQLTool{
		Endpoint:      cfg.Text2SQLEndpoint,
		AllowedTables: []string{"financials", "orders", "balance_sheet"},
		MaxRetries:    2,
	})

	engine := server.SetupRouter(r) // 关键修改

	srv := &http.Server{
		Addr:    ":" + cfg.Port,
		Handler: engine,
	}

	go func() {
		log.Printf("Go Tool Server starting on port %s", cfg.Port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("listen: %s", err)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Fatal("Server forced to shutdown:", err)
	}
	log.Println("Server exiting")
}

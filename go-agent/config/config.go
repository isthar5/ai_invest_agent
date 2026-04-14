package config

import "os"

type Config struct {
	RAGEndpoint   string
	QuantEndpoint string
	Port          string
}

func Load() *Config {
	return &Config{
		RAGEndpoint:   getEnv("RAG_ENDPOINT", "http://localhost:8000/rag"),
		QuantEndpoint: getEnv("QUANT_ENDPOINT", "http://localhost:8000/quant"),
		Port:          getEnv("PORT", "8080"),
	}
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}
package config

import "os"

type Config struct {
	RAGEndpoint      string
	QuantEndpoint    string
	Text2SQLEndpoint string // 新增：Text-to-SQL 服务地址
	Port             string
}

func Load() *Config {
	return &Config{
		RAGEndpoint:      getEnv("RAG_ENDPOINT", "http://localhost:8000/rag"),
		QuantEndpoint:    getEnv("QUANT_ENDPOINT", "http://localhost:8000/quant"),
		Text2SQLEndpoint: getEnv("TEXT2SQL_ENDPOINT", "http://localhost:8001"),
		Port:             getEnv("PORT", "8080"),
	}
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

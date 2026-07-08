package router

import (
	"fmt"
	"go-agent/schema"
)

type Tool interface {
	Name() string
	Schema() schema.ToolSchema
	Run(input map[string]interface{}) (interface{}, error)
}

type Router struct {
	tools map[string]Tool
}

func NewRouter() *Router {
	return &Router{
		tools: make(map[string]Tool),
	}
}

func (r *Router) Register(t Tool) {
	r.tools[t.Name()] = t
}

func (r *Router) Call(name string, input map[string]interface{}) (interface{}, error) {
	tool, ok := r.tools[name]
	if !ok {
		return nil, fmt.Errorf("tool not found: %s", name)
	}

	// 参数校验
	s := tool.Schema()
	for p := range s.Params {
		if _, ok := input[p]; !ok {
			return nil, fmt.Errorf("missing param: %s", p)
		}
	}

	return tool.Run(input)
}

func (r *Router) ListTools() []schema.ToolSchema {
	var list []schema.ToolSchema
	for _, t := range r.tools {
		list = append(list, t.Schema())
	}
	return list
}
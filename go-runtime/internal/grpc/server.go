package grpcserver

import (
	"context"
	"log"
	"net"

	pb "github.com/ai-invest-agent/go-runtime/proto/runtime/v1"
	"github.com/ai-invest-agent/go-runtime/internal/scheduler"
	"google.golang.org/grpc"
	"google.golang.org/grpc/reflection"
)

// Server wraps the gRPC server and Scheduler.
type Server struct {
	pb.UnimplementedSchedulerServiceServer
	srv       *grpc.Server
	scheduler *scheduler.Scheduler
}

// New creates a new gRPC server with the given scheduler.
func New(sched *scheduler.Scheduler) *Server {
	return &Server{scheduler: sched}
}

// SubmitTask implements the synchronous RPC.
func (s *Server) SubmitTask(ctx context.Context, task *pb.Task) (*pb.TaskResult, error) {
	log.Printf("[grpc] SubmitTask: id=%s skill=%s timeout=%.0fms",
		task.TaskId, task.Skill, task.TimeoutMs)
	return s.scheduler.Submit(ctx, task)
}

// SubmitTaskStream implements the streaming RPC (returns 1 result for now).
func (s *Server) SubmitTaskStream(task *pb.Task, stream pb.SchedulerService_SubmitTaskStreamServer) error {
	log.Printf("[grpc] SubmitTaskStream: id=%s skill=%s", task.TaskId, task.Skill)
	result, err := s.scheduler.Submit(stream.Context(), task)
	if err != nil {
		return err
	}
	return stream.Send(result)
}

// CancelTask implements the cancellation RPC.
func (s *Server) CancelTask(ctx context.Context, req *pb.CancelTaskRequest) (*pb.CancelTaskResponse, error) {
	log.Printf("[grpc] CancelTask: id=%s", req.TaskId)
	success := s.scheduler.CancelTask(req.TaskId)

	errMsg := ""
	if !success {
		errMsg = "task not found or already completed"
	}

	return &pb.CancelTaskResponse{
		Success: success,
		Error:   errMsg,
	}, nil
}

// Start runs the gRPC server on the given port.
func (s *Server) Start(port string) error {
	lis, err := net.Listen("tcp", ":"+port)
	if err != nil {
		return err
	}

	s.srv = grpc.NewServer()
	pb.RegisterSchedulerServiceServer(s.srv, s)
	reflection.Register(s.srv) // for grpcurl debugging

	log.Printf("[grpc] server listening on :%s", port)
	return s.srv.Serve(lis)
}

// Stop gracefully stops the gRPC server.
func (s *Server) Stop() {
	if s.srv != nil {
		s.srv.GracefulStop()
	}
}

.PHONY: proto build run clean

# Generate protobuf code
proto:
	protoc \
		--proto_path=proto \
		--go_out=proto --go_opt=paths=source_relative \
		--go-grpc_out=proto --go-grpc_opt=paths=source_relative \
		proto/runtime/v1/task.proto
	@echo "Proto generated"

# Build Go binary
build: proto
	go build -o bin/scheduler ./cmd/scheduler

# Run Go Runtime
run: build
	./bin/scheduler

# Clean
clean:
	rm -rf bin/
	rm -f proto/runtime/v1/*.pb.go

# Download deps
deps:
	go mod tidy
	go mod download

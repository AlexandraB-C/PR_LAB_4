#!/bin/bash

echo "=== QUICK SYSTEM TEST ==="

# function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# function to wait for service
wait_for_service() {
    local url=$1
    local max_attempts=12
    local attempt=1

    echo "waiting for $url..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url/health" >/dev/null 2>&1; then
            echo "✓ $url is ready"
            return 0
        fi
        echo "  attempt $attempt/$max_attempts..."
        sleep 5
        ((attempt++))
    done

    echo "❌ $url failed to start"
    return 1
}

# function to test write
test_write() {
    local key=$1
    local value=$2
    echo "writing $key = $value"

    response=$(curl -s -X POST http://localhost:8000/write \
        -H "Content-Type: application/json" \
        -d "{\"key\":\"$key\",\"value\":\"$value\"}" 2>/dev/null)

    if echo "$response" | grep -q '"success":true'; then
        echo "✓ write successful"
        return 0
    else
        echo "❌ write failed: $response"
        return 1
    fi
}

# function to test read from node
test_read() {
    local url=$1
    local key=$2
    local expected=$3

    response=$(curl -s "$url/read/$key" 2>/dev/null)

    if echo "$response" | grep -q "\"value\":\"$expected\""; then
        echo "✓ $url has correct value"
        return 0
    else
        echo "❌ $url has wrong value: $response"
        return 1
    fi
}

# start system
echo "building and starting system..."
if ! docker-compose up -d --build >/dev/null 2>&1; then
    echo "❌ failed to start system"
    exit 1
fi
echo "✓ system started"

# wait for all services
SERVICES=(
    "http://localhost:8000"
    "http://localhost:8001"
    "http://localhost:8002"
    "http://localhost:8003"
    "http://localhost:8004"
    "http://localhost:8005"
)

for service in "${SERVICES[@]}"; do
    if ! wait_for_service "$service"; then
        echo "❌ services not ready, cleaning up..."
        docker-compose down >/dev/null 2>&1
        exit 1
    fi
done

echo "all services ready!"

# test basic write and read
echo ""
echo "testing basic operations..."

if ! test_write "testkey" "testvalue"; then
    echo "❌ basic write failed"
    docker-compose down >/dev/null 2>&1
    exit 1
fi

echo "waiting for replication..."
sleep 3

# test read from all nodes
SUCCESS=true
for service in "${SERVICES[@]}"; do
    if ! test_read "$service" "testkey" "testvalue"; then
        SUCCESS=false
    fi
done

# test write rejection on follower
echo ""
echo "testing write rejection on follower..."
response=$(curl -s -X POST http://localhost:8001/write \
    -H "Content-Type: application/json" \
    -d '{"key":"reject","value":"test"}' 2>/dev/null)

if echo "$response" | grep -q "403"; then
    echo "✓ follower correctly rejects writes"
else
    echo "❌ follower should reject writes: $response"
    SUCCESS=false
fi

# cleanup
echo ""
echo "cleaning up..."
docker-compose down >/dev/null 2>&1

# final result
echo ""
if [ "$SUCCESS" = true ]; then
    echo "🎉 ALL TESTS PASSED!"
    exit 0
else
    echo "❌ SOME TESTS FAILED"
    exit 1
fi

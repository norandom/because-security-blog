#!/usr/bin/env python3
"""
Test runner script for local development
"""
import subprocess
import sys
import os

def main():
    """Run tests with coverage and proper environment"""
    
    # Set test environment variables
    os.environ["CACHE_ENABLED"] = "false"  # Disable cache for tests
    os.environ["RATE_LIMIT_ENABLED"] = "false"  # Disable rate limiting for tests
    os.environ["LOG_LEVEL"] = "ERROR"  # Reduce log noise
    
    # Test commands to run
    commands = [
        # Run unit tests
        ["uv", "run", "pytest", "tests/", "-v", "--tb=short"],
        
        # Test app import
        ["uv", "run", "python", "-c", "from blog_backend.main import app; print('✅ App imports successfully')"],
        
        # Test query builder specifically
        ["uv", "run", "python", "-c", "from blog_backend.query_builder import QueryBuilder; print('✅ Query builder imports successfully')"],
        
        # Test services
        ["uv", "run", "python", "-c", "from blog_backend.services import PostService; print('✅ Services import successfully')"],
    ]
    
    print("🧪 Running test suite...")
    
    for i, cmd in enumerate(commands, 1):
        print(f"\n📋 Step {i}/{len(commands)}: {' '.join(cmd[2:])}")
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=False)
        except subprocess.CalledProcessError as e:
            print(f"❌ Test failed with exit code {e.returncode}")
            sys.exit(e.returncode)
    
    print("\n🎉 All tests passed successfully!")

if __name__ == "__main__":
    main()
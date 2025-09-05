#!/usr/bin/env python3
"""
Performance profiling utilities for Claude-Slack MCP tools

Enable by setting environment variable: CLAUDE_SLACK_PERF=1
"""

import time
import functools
import asyncio
import json
from typing import Dict, Any, Optional, Callable
from collections import defaultdict
import os

# Only enable if environment variable is set
PERF_ENABLED = os.getenv('CLAUDE_SLACK_PERF', '').lower() in ('1', 'true', 'yes')

# Performance data storage
perf_data = defaultdict(list)
PERF_LOG_PATH = os.path.expanduser("~/.claude/claude-slack/logs/performance.json")


def ensure_perf_log_dir():
    """Ensure performance log directory exists"""
    os.makedirs(os.path.dirname(PERF_LOG_PATH), exist_ok=True)


def timing_decorator(component: str = None):
    """
    Decorator to measure execution time of functions.
    
    Args:
        component: Component name for grouping metrics
    """
    def decorator(func):
        # If performance monitoring disabled, return function unchanged
        if not PERF_ENABLED:
            return func
            
        component_name = component or func.__module__.split('.')[-1]
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = None
            error = None
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                elapsed = (time.perf_counter() - start_time) * 1000  # ms
                
                # Record timing
                perf_entry = {
                    'component': component_name,
                    'function': func.__name__,
                    'duration_ms': round(elapsed, 2),
                    'timestamp': time.time(),
                    'error': error
                }
                
                # Add args info for specific functions
                if func.__name__ in ['execute_tool', 'call_tool']:
                    if 'name' in kwargs:
                        perf_entry['tool_name'] = kwargs['name']
                    elif len(args) > 1:
                        perf_entry['tool_name'] = args[1] if func.__name__ == 'call_tool' else args[0]
                
                perf_data[component_name].append(perf_entry)
                
                # Write to log file if slow
                if elapsed > 100:  # Log slow operations (>100ms)
                    ensure_perf_log_dir()
                    try:
                        with open(PERF_LOG_PATH, 'a') as f:
                            f.write(json.dumps(perf_entry) + '\n')
                    except:
                        pass  # Don't fail on logging errors
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = None
            error = None
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error = str(e)
                raise
            finally:
                elapsed = (time.perf_counter() - start_time) * 1000  # ms
                
                perf_entry = {
                    'component': component_name,
                    'function': func.__name__,
                    'duration_ms': round(elapsed, 2),
                    'timestamp': time.time(),
                    'error': error
                }
                
                perf_data[component_name].append(perf_entry)
                
                if elapsed > 100:
                    ensure_perf_log_dir()
                    try:
                        with open(PERF_LOG_PATH, 'a') as f:
                            f.write(json.dumps(perf_entry) + '\n')
                    except:
                        pass
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def get_performance_summary() -> Dict[str, Any]:
    """
    Get a summary of performance metrics.
    
    Returns:
        Dict with performance statistics by component
    """
    summary = {}
    
    for component, entries in perf_data.items():
        if not entries:
            continue
            
        durations = [e['duration_ms'] for e in entries]
        errors = [e for e in entries if e.get('error')]
        
        summary[component] = {
            'total_calls': len(entries),
            'total_errors': len(errors),
            'avg_duration_ms': round(sum(durations) / len(durations), 2),
            'min_duration_ms': round(min(durations), 2),
            'max_duration_ms': round(max(durations), 2),
            'slow_calls': len([d for d in durations if d > 100]),
            'by_function': {}
        }
        
        # Group by function
        func_groups = defaultdict(list)
        for entry in entries:
            func_groups[entry['function']].append(entry['duration_ms'])
        
        for func_name, func_durations in func_groups.items():
            summary[component]['by_function'][func_name] = {
                'calls': len(func_durations),
                'avg_ms': round(sum(func_durations) / len(func_durations), 2),
                'max_ms': round(max(func_durations), 2)
            }
    
    return summary


def reset_performance_data():
    """Reset performance data"""
    global perf_data
    perf_data = defaultdict(list)


def save_performance_report(filepath: Optional[str] = None):
    """
    Save a detailed performance report.
    
    Args:
        filepath: Optional path to save report
    """
    filepath = filepath or os.path.expanduser("~/.claude/claude-slack/logs/perf_report.json")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    report = {
        'timestamp': time.time(),
        'summary': get_performance_summary(),
        'details': dict(perf_data)
    }
    
    with open(filepath, 'w') as f:
        json.dump(report, f, indent=2)
    
    return filepath


# Context manager for timing blocks
class Timer:
    """Context manager for timing code blocks"""
    
    def __init__(self, name: str, component: str = "manual"):
        self.name = name
        self.component = component
        self.start_time = None
        self.enabled = PERF_ENABLED
    
    def __enter__(self):
        if self.enabled:
            self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enabled:
            return
            
        elapsed = (time.perf_counter() - self.start_time) * 1000
        
        perf_entry = {
            'component': self.component,
            'function': self.name,
            'duration_ms': round(elapsed, 2),
            'timestamp': time.time(),
            'error': str(exc_val) if exc_val else None
        }
        
        perf_data[self.component].append(perf_entry)
        
        if elapsed > 100:
            ensure_perf_log_dir()
            try:
                with open(PERF_LOG_PATH, 'a') as f:
                    f.write(json.dumps(perf_entry) + '\n')
            except:
                pass
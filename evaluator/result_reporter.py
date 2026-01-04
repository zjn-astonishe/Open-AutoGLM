"""Result reporter for Android World test results."""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import datetime
import statistics


class AndroidWorldResultReporter:
    """Generates reports and analysis for Android World test results."""
    
    def __init__(self, output_dir: str = "output/android_world_results"):
        """
        Initialize the result reporter.
        
        Args:
            output_dir: Directory to save reports
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    def generate_benchmark_report(self, 
                                results: List[Dict[str, Any]], 
                                total_time: float) -> Dict[str, Any]:
        """
        Generate a comprehensive benchmark report.
        
        Args:
            results: List of task execution results
            total_time: Total execution time
            
        Returns:
            Comprehensive benchmark report
        """
        print("\n📊 Generating benchmark report...")
        
        # Basic statistics
        total_tasks = len(results)
        successful_tasks = sum(1 for r in results if r.get('success', False))
        failed_tasks = total_tasks - successful_tasks
        success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0.0
        
        # Task family breakdown
        family_stats = self._analyze_by_family(results)
        
        # Performance metrics
        performance_metrics = self._calculate_performance_metrics(results)
        
        # Error analysis
        error_analysis = self._analyze_errors(results)
        
        # Score distribution
        score_distribution = self._analyze_score_distribution(results)
        
        # Time analysis
        time_analysis = self._analyze_execution_times(results, total_time)
        
        # Calculate average time per task
        average_time_per_task = total_time / total_tasks if total_tasks > 0 else 0.0
        
        report = {
            'summary': {
                'total_tasks': total_tasks,
                'successful_tasks': successful_tasks,
                'failed_tasks': failed_tasks,
                'success_rate': success_rate,
                'total_time': total_time,
                'average_time_per_task': average_time_per_task,
                'timestamp': datetime.now().isoformat()
            },
            'family_breakdown': family_stats,
            'performance_metrics': performance_metrics,
            'error_analysis': error_analysis,
            'score_distribution': score_distribution,
            'time_analysis': time_analysis,
            'detailed_results': results
        }
        
        # Save report
        self._save_report(report, "benchmark_report")
        
        # Print summary
        self._print_benchmark_summary(report)
        
        return report
    
    def generate_task_report(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a report for a single task.
        
        Args:
            result: Single task execution result
            
        Returns:
            Task report
        """
        task_name = result.get('task_name', 'unknown')
        
        report = {
            'task_info': {
                'name': task_name,
                'family': result.get('family', 'unknown'),
                'goal': result.get('task_goal', ''),
                'timestamp': result.get('timestamp', datetime.now().isoformat())
            },
            'execution': {
                'success': result.get('success', False),
                'total_time': result.get('total_time', 0),
                'agent_execution_time': result.get('agent_result', {}).get('execution_time', 0),
                'num_actions': result.get('evaluation', {}).get('num_actions', 0)
            },
            'evaluation': result.get('evaluation', {}),
            'agent_result': result.get('agent_result', {}),
            'metadata': result.get('metadata', {})
        }
        
        # Save individual task report
        self._save_report(report, f"task_{task_name}")
        
        return report
    
    def _analyze_by_family(self, results: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Analyze results by task family."""
        family_data = {}
        
        for result in results:
            family = result.get('family', 'unknown')
            
            if family not in family_data:
                family_data[family] = {
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'scores': [],
                    'times': [],
                    'tasks': []
                }
            
            family_stats = family_data[family]
            family_stats['total'] += 1
            family_stats['tasks'].append(result.get('task_name', 'unknown'))
            
            if result.get('success', False):
                family_stats['successful'] += 1
            else:
                family_stats['failed'] += 1
            
            # Collect scores and times
            evaluation = result.get('evaluation', {})
            if 'evaluation_score' in evaluation:
                family_stats['scores'].append(evaluation['evaluation_score'])
            
            if 'total_time' in result:
                family_stats['times'].append(result['total_time'])
        
        # Calculate statistics for each family
        for family, stats in family_data.items():
            stats['success_rate'] = stats['successful'] / stats['total'] if stats['total'] > 0 else 0.0
            
            if stats['scores']:
                stats['average_score'] = statistics.mean(stats['scores'])
                stats['median_score'] = statistics.median(stats['scores'])
                stats['score_std'] = statistics.stdev(stats['scores']) if len(stats['scores']) > 1 else 0.0
            
            if stats['times']:
                stats['average_time'] = statistics.mean(stats['times'])
                stats['median_time'] = statistics.median(stats['times'])
        
        return family_data
    
    def _calculate_performance_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall performance metrics."""
        scores = []
        times = []
        action_counts = []
        
        for result in results:
            evaluation = result.get('evaluation', {})
            
            if 'evaluation_score' in evaluation:
                scores.append(evaluation['evaluation_score'])
            
            if 'total_time' in result:
                times.append(result['total_time'])
            
            if 'num_actions' in evaluation:
                action_counts.append(evaluation['num_actions'])
        
        metrics = {}
        
        if scores:
            metrics['score_stats'] = {
                'mean': statistics.mean(scores),
                'median': statistics.median(scores),
                'std': statistics.stdev(scores) if len(scores) > 1 else 0.0,
                'min': min(scores),
                'max': max(scores)
            }
        
        if times:
            metrics['time_stats'] = {
                'mean': statistics.mean(times),
                'median': statistics.median(times),
                'std': statistics.stdev(times) if len(times) > 1 else 0.0,
                'min': min(times),
                'max': max(times)
            }
        
        if action_counts:
            metrics['action_stats'] = {
                'mean': statistics.mean(action_counts),
                'median': statistics.median(action_counts),
                'std': statistics.stdev(action_counts) if len(action_counts) > 1 else 0.0,
                'min': min(action_counts),
                'max': max(action_counts)
            }
        
        return metrics
    
    def _analyze_errors(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze error patterns."""
        error_types = {}
        failed_tasks = []
        
        for result in results:
            if not result.get('success', False):
                task_name = result.get('task_name', 'unknown')
                failed_tasks.append(task_name)
                
                # Categorize errors
                error_msg = result.get('error', '')
                if not error_msg:
                    error_msg = result.get('evaluation', {}).get('error', '')
                if not error_msg:
                    error_msg = result.get('agent_result', {}).get('error', 'Unknown error')
                
                # Simple error categorization
                error_category = self._categorize_error(error_msg)
                
                if error_category not in error_types:
                    error_types[error_category] = {
                        'count': 0,
                        'tasks': [],
                        'examples': []
                    }
                
                error_types[error_category]['count'] += 1
                error_types[error_category]['tasks'].append(task_name)
                if len(error_types[error_category]['examples']) < 3:
                    error_types[error_category]['examples'].append(error_msg)
        
        return {
            'total_failures': len(failed_tasks),
            'failed_tasks': failed_tasks,
            'error_categories': error_types
        }
    
    def _categorize_error(self, error_msg: str) -> str:
        """Categorize error message into types."""
        error_msg_lower = error_msg.lower()
        
        if 'timeout' in error_msg_lower:
            return 'timeout'
        elif 'connection' in error_msg_lower or 'adb' in error_msg_lower:
            return 'connection'
        elif 'element not found' in error_msg_lower or 'ui element' in error_msg_lower:
            return 'ui_element'
        elif 'action failed' in error_msg_lower:
            return 'action_execution'
        elif 'evaluation' in error_msg_lower:
            return 'evaluation'
        elif 'agent' in error_msg_lower:
            return 'agent_error'
        else:
            return 'other'
    
    def _analyze_score_distribution(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze score distribution."""
        scores = []
        
        for result in results:
            evaluation = result.get('evaluation', {})
            if 'evaluation_score' in evaluation:
                scores.append(evaluation['evaluation_score'])
        
        if not scores:
            return {'message': 'No scores available'}
        
        # Create score buckets
        buckets = {
            '0.0-0.2': 0,
            '0.2-0.4': 0,
            '0.4-0.6': 0,
            '0.6-0.8': 0,
            '0.8-1.0': 0
        }
        
        for score in scores:
            if score < 0.2:
                buckets['0.0-0.2'] += 1
            elif score < 0.4:
                buckets['0.2-0.4'] += 1
            elif score < 0.6:
                buckets['0.4-0.6'] += 1
            elif score < 0.8:
                buckets['0.6-0.8'] += 1
            else:
                buckets['0.8-1.0'] += 1
        
        return {
            'total_scores': len(scores),
            'distribution': buckets,
            'perfect_scores': sum(1 for s in scores if s >= 1.0),
            'zero_scores': sum(1 for s in scores if s == 0.0)
        }
    
    def _analyze_execution_times(self, results: List[Dict[str, Any]], total_time: float) -> Dict[str, Any]:
        """Analyze execution time patterns."""
        task_times = []
        agent_times = []
        
        for result in results:
            if 'total_time' in result:
                task_times.append(result['total_time'])
            
            agent_result = result.get('agent_result', {})
            if 'execution_time' in agent_result:
                agent_times.append(agent_result['execution_time'])
        
        analysis = {
            'total_benchmark_time': total_time,
            'total_tasks': len(results)
        }
        
        if task_times:
            analysis['task_time_stats'] = {
                'mean': statistics.mean(task_times),
                'median': statistics.median(task_times),
                'min': min(task_times),
                'max': max(task_times),
                'total': sum(task_times)
            }
        
        if agent_times:
            analysis['agent_time_stats'] = {
                'mean': statistics.mean(agent_times),
                'median': statistics.median(agent_times),
                'min': min(agent_times),
                'max': max(agent_times),
                'total': sum(agent_times)
            }
        
        return analysis
    
    def _save_report(self, report: Dict[str, Any], filename_prefix: str):
        """Save report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename_prefix}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False, default=str)
            print(f"📄 Report saved to: {filepath}")
        except Exception as e:
            print(f"⚠️ Failed to save report to {filepath}: {e}")
    
    def _print_benchmark_summary(self, report: Dict[str, Any]):
        """Print a formatted benchmark summary."""
        summary = report['summary']
        family_breakdown = report['family_breakdown']
        performance = report['performance_metrics']
        
        print("\n" + "="*60)
        print("🏆 ANDROID WORLD BENCHMARK RESULTS")
        print("="*60)
        
        print(f"\n📊 OVERALL SUMMARY:")
        print(f"   Total Tasks: {summary['total_tasks']}")
        print(f"   Successful: {summary['successful_tasks']} ({summary['success_rate']:.1%})")
        print(f"   Failed: {summary['failed_tasks']}")
        print(f"   Total Time: {summary['total_time']:.1f}s")
        
        if 'score_stats' in performance:
            score_stats = performance['score_stats']
            print(f"\n📈 PERFORMANCE METRICS:")
            print(f"   Average Score: {score_stats['mean']:.3f}")
            print(f"   Median Score: {score_stats['median']:.3f}")
            print(f"   Score Range: {score_stats['min']:.3f} - {score_stats['max']:.3f}")
        
        if family_breakdown:
            print(f"\n📋 FAMILY BREAKDOWN:")
            for family, stats in family_breakdown.items():
                print(f"   {family}:")
                print(f"     Tasks: {stats['total']} | Success: {stats['successful']} ({stats['success_rate']:.1%})")
                if 'average_score' in stats:
                    print(f"     Avg Score: {stats['average_score']:.3f}")
        
        if 'error_categories' in report['error_analysis']:
            error_cats = report['error_analysis']['error_categories']
            if error_cats:
                print(f"\n❌ TOP ERROR CATEGORIES:")
                sorted_errors = sorted(error_cats.items(), key=lambda x: x[1]['count'], reverse=True)
                for error_type, error_info in sorted_errors[:3]:
                    print(f"   {error_type}: {error_info['count']} occurrences")
        
        print("\n" + "="*60)
    
    def export_csv_summary(self, results: List[Dict[str, Any]], filename: Optional[str] = None) -> str:
        """
        Export results summary to CSV format.
        
        Args:
            results: List of task results
            filename: Optional filename (auto-generated if None)
            
        Returns:
            Path to the saved CSV file
        """
        import csv
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"android_world_results_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'task_name', 'family', 'success', 'evaluation_score', 
                    'num_actions', 'total_time', 'agent_execution_time', 'error'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for result in results:
                    evaluation = result.get('evaluation', {})
                    agent_result = result.get('agent_result', {})
                    
                    row = {
                        'task_name': result.get('task_name', ''),
                        'family': result.get('family', ''),
                        'success': result.get('success', False),
                        'evaluation_score': evaluation.get('evaluation_score', 0.0),
                        'num_actions': evaluation.get('num_actions', 0),
                        'total_time': result.get('total_time', 0.0),
                        'agent_execution_time': agent_result.get('execution_time', 0.0),
                        'error': result.get('error', '')
                    }
                    writer.writerow(row)
            
            print(f"📊 CSV summary exported to: {filepath}")
            return filepath
            
        except Exception as e:
            print(f"⚠️ Failed to export CSV: {e}")
            return ""
    
    def compare_runs(self, 
                    current_results: List[Dict[str, Any]], 
                    previous_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare current results with previous run results.
        
        Args:
            current_results: Current benchmark results
            previous_results: Previous benchmark results
            
        Returns:
            Comparison analysis
        """
        current_summary = self._calculate_summary_stats(current_results)
        previous_summary = self._calculate_summary_stats(previous_results)
        
        comparison = {
            'current': current_summary,
            'previous': previous_summary,
            'changes': {
                'success_rate_change': current_summary['success_rate'] - previous_summary['success_rate'],
                'score_change': current_summary.get('average_score', 0) - previous_summary.get('average_score', 0),
                'time_change': current_summary.get('average_time', 0) - previous_summary.get('average_time', 0)
            }
        }
        
        return comparison
    
    def _calculate_summary_stats(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate summary statistics for a set of results."""
        total = len(results)
        successful = sum(1 for r in results if r.get('success', False))
        
        scores = [r.get('evaluation', {}).get('evaluation_score', 0) for r in results 
                 if 'evaluation' in r and 'evaluation_score' in r['evaluation']]
        times = [r.get('total_time', 0) for r in results if 'total_time' in r]
        
        stats = {
            'total_tasks': total,
            'successful_tasks': successful,
            'success_rate': successful / total if total > 0 else 0.0
        }
        
        if scores:
            stats['average_score'] = statistics.mean(scores)
        
        if times:
            stats['average_time'] = statistics.mean(times)
        
        return stats

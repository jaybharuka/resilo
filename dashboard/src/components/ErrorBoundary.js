import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    const { fallbackTitle = 'Something went wrong', compact = false } = this.props;

    if (compact) {
      return (
        <div className="flex items-center gap-2 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
          <AlertTriangle size={14} className="shrink-0" />
          <span>{fallbackTitle}</span>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="ml-auto text-red-500 hover:text-red-700"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      );
    }

    return (
      <div className="flex flex-col items-center justify-center min-h-[300px] p-8 text-center">
        <div className="w-12 h-12 rounded-full bg-red-50 flex items-center justify-center mb-4">
          <AlertTriangle size={22} className="text-red-500" />
        </div>
        <h3 className="text-base font-semibold text-slate-900 mb-1">{fallbackTitle}</h3>
        <p className="text-sm text-slate-500 mb-5 max-w-sm">
          {this.state.error?.message || 'An unexpected error occurred in this panel.'}
        </p>
        <button
          onClick={() => this.setState({ hasError: false, error: null })}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <RefreshCw size={13} />
          Try again
        </button>
      </div>
    );
  }
}

import React, { useState, useEffect } from 'react';
import { apiService, systemApi, actionsApi } from '../services/api';
import { toast } from 'react-hot-toast';
import { Bot, AlertTriangle, Sparkles, BarChart3, Target } from 'lucide-react';

const AIInsights = () => {
  const [aiData, setAiData] = useState({
    health: { status: 'loading', accuracy: 0, response_time: 0 },
    anomalies: [],
    predictions: []
  });

  useEffect(() => {
    const fetchAIData = async () => {
      try {
        const [aiData, anomaliesData, predictiveData] = await Promise.all([
          apiService.getAiInsights(),
          apiService.getAlerts(),
          systemApi.getPredictive().catch(() => [])
        ]);

        setAiData({
          health: aiData || {},
          anomalies: anomaliesData || [],
          predictions: predictiveData || []
        });
      } catch (error) {
        console.error('Error fetching AI data:', error);
      }
    };

    fetchAIData();
    const interval = setInterval(fetchAIData, 3000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy': return 'text-green-400';
      case 'warning': return 'text-yellow-400';
      case 'critical': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getStatusBg = (status) => {
    switch (status) {
      case 'healthy': return 'bg-green-600/20 border-green-500/30';
      case 'warning': return 'bg-yellow-600/20 border-yellow-500/30';
      case 'critical': return 'bg-red-600/20 border-red-500/30';
      default: return 'bg-gray-600/20 border-gray-500/30';
    }
  };

  return (
    <div className="p-6">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-gray-900 mb-2">AI Insights</h2>
        <p className="text-gray-600">Artificial Intelligence monitoring and predictions</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Bot size={18} className="mr-2 text-blue-600" />
            AI Health
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Status</span>
              <div className="flex items-center space-x-2">
                <div className={`w-3 h-3 rounded-full animate-pulse ${
                  aiData.health.status === 'healthy' ? 'bg-green-400' :
                  aiData.health.status === 'warning' ? 'bg-yellow-400' : 'bg-red-400'
                }`}></div>
                <span className={`font-medium capitalize ${getStatusColor(aiData.health.status).replace('400', '600')}`}>
                  {aiData.health.status}
                </span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Accuracy</span>
              <span className="text-blue-600 font-medium">{aiData.health.accuracy}%</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Response Time</span>
              <span className="text-purple-600 font-medium">{aiData.health.response_time}ms</span>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <AlertTriangle size={18} className="mr-2 text-yellow-500" />
            Anomalies
          </h3>
          <div className="space-y-3">
            {aiData.anomalies.length > 0 ? (
              aiData.anomalies.slice(0, 3).map((anomaly, index) => (
                <div key={index} className={`p-3 rounded-lg border ${getStatusBg(anomaly.severity).replace('600/20', '50').replace('500/30', '200')}`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-900 font-medium">{anomaly.type}</span>
                    <span className={`text-xs ${getStatusColor(anomaly.severity).replace('400', '700')} capitalize`}>
                      {anomaly.severity}
                    </span>
                  </div>
                  <p className="text-gray-700 text-sm">{anomaly.description}</p>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-500 py-4">
                No anomalies detected
              </div>
            )}
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Sparkles size={18} className="mr-2 text-purple-500" />
            Predictions
          </h3>
          <div className="space-y-3">
            {aiData.predictions.length > 0 ? (
              aiData.predictions.slice(0, 3).map((prediction, index) => (
                <div key={index} className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-gray-900 font-medium">{prediction.metric}</span>
                    <span className="text-blue-700 text-sm">{prediction.timeframe}</span>
                  </div>
                  <p className="text-gray-700 text-sm">{prediction.prediction}</p>
                  <div className="flex items-center mt-2">
                    <span className="text-xs text-gray-500 mr-2">Confidence:</span>
                    <div className="flex-1 bg-gray-100 rounded-full h-1">
                      <div 
                        className="h-1 bg-blue-600 rounded-full"
                        style={{ width: `${prediction.confidence}%` }}
                      ></div>
                    </div>
                    <span className="text-xs text-blue-700 ml-2">{prediction.confidence}%</span>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center text-gray-500 py-4">
                No predictions available
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <BarChart3 size={18} className="mr-2 text-blue-500" />
            AI Performance Metrics
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Model Accuracy</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-100 rounded-full h-2">
                  <div 
                    className="h-2 bg-green-600 rounded-full transition-all duration-500"
                    style={{ width: `${aiData.health.accuracy}%` }}
                  ></div>
                </div>
                <span className="text-green-700 font-medium">{aiData.health.accuracy}%</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Response Time</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-100 rounded-full h-2">
                  <div 
                    className="h-2 bg-blue-600 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(aiData.health.response_time / 10, 100)}%` }}
                  ></div>
                </div>
                <span className="text-blue-700 font-medium">{aiData.health.response_time}ms</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-700">Prediction Success</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-100 rounded-full h-2">
                  <div className="h-2 bg-purple-600 rounded-full transition-all duration-500 w-4/5"></div>
                </div>
                <span className="text-purple-700 font-medium">87%</span>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="text-xl font-semibold text-gray-900 mb-4 flex items-center">
            <Target size={18} className="mr-2 text-indigo-500" />
            AI Actions
          </h3>
          <div className="space-y-3">
            <button
              onClick={async () => {
                const t = toast.loading('Retraining models...');
                try {
                  const res = await actionsApi.retrainModels();
                  toast.success(res?.message || 'Model retraining started', { id: t });
                } catch (e) {
                  toast.error('Failed to start retraining', { id: t });
                }
              }}
              className="w-full bg-white text-blue-700 border border-blue-200 hover:bg-blue-50 px-4 py-2 rounded-md transition-colors duration-150"
            >
              Retrain Models
            </button>
            <button
              onClick={async () => {
                const t = toast.loading('Running diagnostics...');
                try {
                  const res = await actionsApi.runDiagnostics();
                  toast.success(res?.message || 'Diagnostics started', { id: t });
                } catch (e) {
                  toast.error('Failed to run diagnostics', { id: t });
                }
              }}
              className="w-full bg-white text-green-700 border border-green-200 hover:bg-green-50 px-4 py-2 rounded-md transition-colors duration-150"
            >
              Run Diagnostics
            </button>
            <button
              onClick={async () => {
                const t = toast.loading('Updating parameters...');
                try {
                  const res = await actionsApi.updateParameters({ temperature: 0.2 });
                  toast.success(res?.message || 'Parameters updated', { id: t });
                } catch (e) {
                  toast.error('Failed to update parameters', { id: t });
                }
              }}
              className="w-full bg-white text-purple-700 border border-purple-200 hover:bg-purple-50 px-4 py-2 rounded-md transition-colors duration-150"
            >
              Update Parameters
            </button>
            <button
              onClick={async () => {
                const t = toast.loading('Exporting insights...');
                try {
                  const res = await actionsApi.exportInsights();
                  toast.success(res?.message || 'Insights export started', { id: t });
                } catch (e) {
                  toast.error('Failed to export insights', { id: t });
                }
              }}
              className="w-full bg-white text-yellow-700 border border-yellow-200 hover:bg-yellow-50 px-4 py-2 rounded-md transition-colors duration-150"
            >
              Export Insights
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AIInsights;
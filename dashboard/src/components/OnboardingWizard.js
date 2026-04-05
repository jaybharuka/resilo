import React, { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Plug, Activity, BellRing } from 'lucide-react';
import { apiService } from '../services/api';

const C = {
  surface: 'rgb(22,20,16)',
  border: 'rgba(42,40,32,1)',
  teal: '#2DD4BF',
  amber: '#F59E0B',
  text1: 'rgb(245,240,232)',
  text3: 'rgb(107,99,87)',
};

function Step({ done, icon, title, detail }) {
  return (
    <div style={{ background: done ? 'rgba(45,212,191,0.08)' : C.surface, border: `1px solid ${done ? 'rgba(45,212,191,0.25)' : C.border}`, borderRadius: 10, padding: 14, display: 'flex', gap: 10 }}>
      <div style={{ color: done ? C.teal : C.text3 }}>{done ? <CheckCircle2 size={16} /> : <Circle size={16} />}</div>
      <div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}><span style={{ color: done ? C.teal : C.amber }}>{icon}</span><span style={{ color: C.text1, fontWeight: 600 }}>{title}</span></div>
        <div style={{ color: C.text3, fontSize: 12, marginTop: 6 }}>{detail}</div>
      </div>
    </div>
  );
}

export default function OnboardingWizard() {
  const [state, setState] = useState({ steps: { connect_first_agent: false, see_live_metrics: false, create_first_alert: false } });
  useEffect(() => { apiService.getOnboardingStatus().then((s) => setState(s || state)); }, []);
  const s = state.steps || {};
  const done = [s.connect_first_agent, s.see_live_metrics, s.create_first_alert].filter(Boolean).length;
  return (
    <div style={{ padding: 24, maxWidth: 900, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <h2 style={{ margin: 0, color: C.text1, fontFamily: "'Outfit', sans-serif" }}>Onboarding Wizard</h2>
      <div style={{ color: C.text3, fontSize: 12 }}>Progress: {done}/3 complete</div>
      <Step done={s.connect_first_agent} icon={<Plug size={14} />} title="Connect first agent" detail="Register at least one active agent for your organization." />
      <Step done={s.see_live_metrics} icon={<Activity size={14} />} title="See live metrics" detail="Confirm metric snapshots are arriving in real-time." />
      <Step done={s.create_first_alert} icon={<BellRing size={14} />} title="Create first alert" detail="Trigger or create an alert to enable remediation actions." />
    </div>
  );
}

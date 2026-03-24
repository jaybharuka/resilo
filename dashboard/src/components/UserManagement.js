import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { userApi, authApi } from '../services/api';
import {
  Users, Plus, Mail, Key, Shield, UserCheck, UserX,
  RefreshCw, X, ChevronDown, Copy, Check, Eye, EyeOff,
  Link2, Trash2, AlertTriangle, Monitor,
} from 'lucide-react';
import toast from 'react-hot-toast';

const MONO = { fontFamily: "'IBM Plex Mono', monospace" };
const UI   = { fontFamily: "'Outfit', sans-serif" };

const ROLE_META = {
  admin:    { label: 'Admin',    color: '#F59E0B', bg: 'rgba(245,158,11,0.12)',  border: 'rgba(245,158,11,0.25)' },
  manager:  { label: 'Manager',  color: '#60A5FA', bg: 'rgba(96,165,250,0.1)',   border: 'rgba(96,165,250,0.2)'  },
  employee: { label: 'Employee', color: '#34D399', bg: 'rgba(52,211,153,0.1)',   border: 'rgba(52,211,153,0.2)'  },
  guest:    { label: 'Guest',    color: '#9CA3AF', bg: 'rgba(156,163,175,0.08)', border: 'rgba(156,163,175,0.18)' },
};

function RoleBadge({ role }) {
  const m = ROLE_META[role] || ROLE_META.employee;
  return (
    <span style={{
      ...MONO, fontSize: '10px', letterSpacing: '0.1em',
      padding: '2px 8px', borderRadius: '10px',
      color: m.color, background: m.bg, border: `1px solid ${m.border}`,
    }}>
      {m.label.toUpperCase()}
    </span>
  );
}

function StatusDot({ active }) {
  return (
    <span style={{
      display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
      background: active ? '#34D399' : '#EF4444',
      boxShadow: active ? '0 0 5px rgba(52,211,153,0.5)' : 'none',
    }} />
  );
}

// ── Modal scaffold ──────────────────────────────────────────────────────────
function Modal({ title, onClose, children }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 9999,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 20,
    }}>
      <div style={{
        background: '#151310', border: '1px solid rgba(245,158,11,0.15)',
        borderRadius: 12, width: '100%', maxWidth: 480,
        boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 22px', borderBottom: '1px solid rgba(245,158,11,0.1)',
        }}>
          <span style={{ ...UI, fontSize: 15, fontWeight: 600, color: '#F5F0E8' }}>{title}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B6357', padding: 4, borderRadius: 6 }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ padding: '22px' }}>{children}</div>
      </div>
    </div>
  );
}

// ── Form field ──────────────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: '#6B6357', display: 'block', marginBottom: 6 }}>
        {label.toUpperCase()}
      </label>
      {children}
    </div>
  );
}

const inputStyle = {
  width: '100%', background: '#0D0C0A', border: '1px solid rgba(42,40,32,0.9)',
  borderRadius: 7, padding: '9px 12px', color: '#F5F0E8',
  ...UI, fontSize: 14, outline: 'none', boxSizing: 'border-box',
};

const selectStyle = { ...inputStyle, appearance: 'none', cursor: 'pointer' };

function PwField({ value, onChange, placeholder = 'Password' }) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{ ...inputStyle, paddingRight: 38 }}
      />
      <button
        type="button"
        onClick={() => setShow(s => !s)}
        style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6B6357' }}
      >
        {show ? <EyeOff size={14} /> : <Eye size={14} />}
      </button>
    </div>
  );
}

function Btn({ children, onClick, variant = 'primary', disabled, style: sx }) {
  const base = {
    ...UI, fontSize: 13, fontWeight: 500, padding: '9px 18px', borderRadius: 7,
    cursor: disabled ? 'not-allowed' : 'pointer', border: 'none', display: 'inline-flex',
    alignItems: 'center', gap: 7, opacity: disabled ? 0.5 : 1, transition: 'opacity 0.15s',
  };
  const variants = {
    primary: { background: '#F59E0B', color: '#0C0B09' },
    ghost:   { background: 'transparent', color: '#6B6357', border: '1px solid rgba(42,40,32,0.9)' },
    danger:  { background: 'rgba(239,68,68,0.15)', color: '#EF4444', border: '1px solid rgba(239,68,68,0.25)' },
  };
  return (
    <button onClick={onClick} disabled={disabled} style={{ ...base, ...variants[variant], ...sx }}>
      {children}
    </button>
  );
}

// ── Create User Modal ───────────────────────────────────────────────────────
function CreateUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ email: '', username: '', password: '', role: 'employee', full_name: '', must_change_password: true });
  const [loading, setLoading] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!form.email || !form.username || !form.password) { toast.error('Email, username and password are required'); return; }
    setLoading(true);
    try {
      const user = await userApi.create(form);
      toast.success(`User ${user.username} created`);
      onCreated(user);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to create user');
    } finally { setLoading(false); }
  };

  return (
    <Modal title="Create New User" onClose={onClose}>
      <Field label="Email"><input style={inputStyle} value={form.email} onChange={e => set('email', e.target.value)} placeholder="user@company.com" /></Field>
      <Field label="Username"><input style={inputStyle} value={form.username} onChange={e => set('username', e.target.value)} placeholder="jsmith" /></Field>
      <Field label="Full Name (optional)"><input style={inputStyle} value={form.full_name} onChange={e => set('full_name', e.target.value)} placeholder="Jane Smith" /></Field>
      <Field label="Role">
        <select style={selectStyle} value={form.role} onChange={e => set('role', e.target.value)}>
          {Object.entries(ROLE_META).map(([r, m]) => <option key={r} value={r}>{m.label}</option>)}
        </select>
      </Field>
      <Field label="Temporary Password"><PwField value={form.password} onChange={v => set('password', v)} placeholder="Min 8 characters" /></Field>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 20 }}>
        <input type="checkbox" checked={form.must_change_password} onChange={e => set('must_change_password', e.target.checked)} />
        <span style={{ ...UI, fontSize: 13, color: '#9CA3AF' }}>Require password change on first login</span>
      </label>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}>{loading ? 'Creating…' : 'Create User'}</Btn>
      </div>
    </Modal>
  );
}

// ── Invite Modal ────────────────────────────────────────────────────────────
function InviteModal({ onClose }) {
  const [form, setForm] = useState({ email: '', role: 'employee', note: '', ttl_hours: 72 });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    setLoading(true);
    try {
      const res = await authApi.createInvite(form);
      setResult(res);
      toast.success('Invite created');
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to create invite');
    } finally { setLoading(false); }
  };

  const copy = () => {
    navigator.clipboard.writeText(result.accept_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (result) {
    return (
      <Modal title="Invite Created" onClose={onClose}>
        <p style={{ ...UI, fontSize: 13, color: '#9CA3AF', marginBottom: 16 }}>
          Share this link with the invitee. It expires in <strong style={{ color: '#F5F0E8' }}>{result.expires_in_hours}h</strong>.
        </p>
        <div style={{ background: '#0D0C0A', border: '1px solid rgba(42,40,32,0.9)', borderRadius: 7, padding: '10px 14px', marginBottom: 16 }}>
          <p style={{ ...MONO, fontSize: 11, color: '#F59E0B', wordBreak: 'break-all', margin: 0 }}>{result.accept_url}</p>
        </div>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Btn variant="ghost" onClick={onClose}>Close</Btn>
          <Btn onClick={copy}>{copied ? <><Check size={14} /> Copied!</> : <><Copy size={14} /> Copy Link</>}</Btn>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="Invite User" onClose={onClose}>
      <Field label="Email (optional — leave blank for generic invite)">
        <input style={inputStyle} value={form.email} onChange={e => set('email', e.target.value)} placeholder="user@company.com" />
      </Field>
      <Field label="Role">
        <select style={selectStyle} value={form.role} onChange={e => set('role', e.target.value)}>
          {Object.entries(ROLE_META).map(([r, m]) => <option key={r} value={r}>{m.label}</option>)}
        </select>
      </Field>
      <Field label="Note (optional)">
        <input style={inputStyle} value={form.note} onChange={e => set('note', e.target.value)} placeholder="Engineering team, Q2 hire…" />
      </Field>
      <Field label="Expires after (hours)">
        <input style={inputStyle} type="number" value={form.ttl_hours} onChange={e => set('ttl_hours', parseInt(e.target.value) || 72)} min={1} max={720} />
      </Field>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}><Link2 size={14} />{loading ? 'Creating…' : 'Generate Invite Link'}</Btn>
      </div>
    </Modal>
  );
}

// ── Edit User Modal ─────────────────────────────────────────────────────────
function EditUserModal({ user, onClose, onUpdated }) {
  const [role, setRole] = useState(user.role);
  const [loading, setLoading] = useState(false);

  const save = async () => {
    setLoading(true);
    try {
      const updated = await userApi.update(user.id, { role });
      toast.success('Role updated');
      onUpdated(updated);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to update user');
    } finally { setLoading(false); }
  };

  return (
    <Modal title={`Edit — ${user.username}`} onClose={onClose}>
      <p style={{ ...UI, fontSize: 13, color: '#9CA3AF', marginBottom: 20 }}>{user.email}</p>
      <Field label="Role">
        <select style={selectStyle} value={role} onChange={e => setRole(e.target.value)}>
          {Object.entries(ROLE_META).map(([r, m]) => <option key={r} value={r}>{m.label}</option>)}
        </select>
      </Field>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={save} disabled={loading}>{loading ? 'Saving…' : 'Save Changes'}</Btn>
      </div>
    </Modal>
  );
}

// ── Reset Password Modal ────────────────────────────────────────────────────
function ResetPwModal({ user, onClose }) {
  const [pw, setPw] = useState('');
  const [force, setForce] = useState(true);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    if (pw.length < 8) { toast.error('Password must be at least 8 characters'); return; }
    setLoading(true);
    try {
      await userApi.resetPassword(user.id, pw, force);
      toast.success(`Password reset for ${user.username}`);
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed to reset password');
    } finally { setLoading(false); }
  };

  return (
    <Modal title={`Reset Password — ${user.username}`} onClose={onClose}>
      <Field label="New Password"><PwField value={pw} onChange={setPw} /></Field>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', marginBottom: 20 }}>
        <input type="checkbox" checked={force} onChange={e => setForce(e.target.checked)} />
        <span style={{ ...UI, fontSize: 13, color: '#9CA3AF' }}>Require password change on next login</span>
      </label>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
        <Btn onClick={submit} disabled={loading}><Key size={14} />{loading ? 'Resetting…' : 'Reset Password'}</Btn>
      </div>
    </Modal>
  );
}

// ── Invites List Panel ──────────────────────────────────────────────────────
function InvitesList({ show }) {
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { setInvites(await authApi.listInvites()); } catch { toast.error('Failed to load invites'); } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (show) load(); }, [show, load]);

  const revoke = async (token) => {
    try {
      await authApi.revokeInvite(token);
      toast.success('Invite revoked');
      setInvites(inv => inv.filter(i => i.token !== token));
    } catch (e) { toast.error(e?.response?.data?.detail || 'Failed'); }
  };

  if (!show) return null;

  const STATUS_COLOR = { pending: '#34D399', used: '#9CA3AF', expired: '#EF4444' };

  return (
    <div style={{ marginTop: 28 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '0.1em', color: '#6B6357' }}>PENDING INVITES</span>
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn variant="ghost" onClick={load} disabled={loading}><RefreshCw size={13} /></Btn>
          <Btn onClick={() => setShowModal(true)}><Plus size={13} />New Invite</Btn>
        </div>
      </div>
      {loading ? (
        <p style={{ ...UI, color: '#6B6357', fontSize: 13 }}>Loading…</p>
      ) : invites.length === 0 ? (
        <p style={{ ...UI, color: '#6B6357', fontSize: 13 }}>No invites yet.</p>
      ) : (
        invites.map(inv => (
          <div key={inv.id} style={{
            display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
            background: '#0D0C0A', borderRadius: 8, marginBottom: 8,
            border: '1px solid rgba(42,40,32,0.7)',
          }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: STATUS_COLOR[inv.status] || '#9CA3AF', display: 'inline-block', flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <span style={{ ...UI, fontSize: 13, color: '#F5F0E8' }}>{inv.email || <em style={{ color: '#6B6357' }}>Generic invite</em>}</span>
              <span style={{ marginLeft: 10 }}><RoleBadge role={inv.role} /></span>
              {inv.note && <span style={{ ...UI, fontSize: 11, color: '#6B6357', marginLeft: 8 }}>{inv.note}</span>}
            </div>
            <span style={{ ...MONO, fontSize: 10, color: '#6B6357' }}>
              {inv.status === 'used' ? 'Used' : inv.status === 'expired' ? 'Expired' : `Expires ${new Date(inv.expires_at).toLocaleDateString()}`}
            </span>
            {inv.status === 'pending' && (
              <button
                onClick={() => { navigator.clipboard.writeText(inv.accept_url); toast.success('Link copied'); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6B6357', padding: 4 }}
                title="Copy invite link"
              >
                <Copy size={13} />
              </button>
            )}
            {inv.status !== 'used' && (
              <button
                onClick={() => revoke(inv.token)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#EF4444', padding: 4, opacity: 0.7 }}
                title="Revoke invite"
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        ))
      )}
      {showModal && <InviteModal onClose={() => { setShowModal(false); load(); }} />}
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────────
export default function UserManagement() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('users'); // 'users' | 'invites'

  const [showCreate, setShowCreate] = useState(false);
  const [editUser, setEditUser] = useState(null);
  const [resetUser, setResetUser] = useState(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { setUsers(await userApi.list()); }
    catch { toast.error('Failed to load users'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const toggleActive = async (user) => {
    try {
      if (user.is_active) {
        await userApi.deactivate(user.id);
        toast.success(`${user.username} deactivated`);
      } else {
        await userApi.update(user.id, { is_active: true });
        toast.success(`${user.username} reactivated`);
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Failed');
    }
    setConfirmDeactivate(null);
  };

  const filtered = users.filter(u => {
    const q = search.toLowerCase();
    return !q || u.email.toLowerCase().includes(q) || u.username.toLowerCase().includes(q) || u.role.includes(q);
  });

  const stats = {
    total: users.length,
    active: users.filter(u => u.is_active).length,
    admins: users.filter(u => u.role === 'admin').length,
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ ...UI, fontSize: 22, fontWeight: 700, color: '#F5F0E8', margin: 0 }}>User Management</h1>
        <p style={{ ...UI, fontSize: 13, color: '#6B6357', marginTop: 4, marginBottom: 0 }}>
          Login accounts, roles &amp; dashboard access — not machine monitoring
        </p>
      </div>

      {/* Info callout */}
      <div style={{
        display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 24,
        background: 'rgba(96,165,250,0.06)', border: '1px solid rgba(96,165,250,0.18)',
        borderRadius: 10, padding: '13px 16px',
      }}>
        <Monitor size={15} color="#60A5FA" style={{ marginTop: 1, flexShrink: 0 }} />
        <p style={{ ...UI, fontSize: 13, color: '#9CA3AF', margin: 0, lineHeight: 1.6 }}>
          Users here can <strong style={{ color: '#F5F0E8' }}>log into this dashboard</strong>.
          To monitor a user's machine metrics (CPU, memory, disk), go to{' '}
          <button
            onClick={() => navigate('/devices')}
            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: '#60A5FA', ...UI, fontSize: 13, textDecoration: 'underline' }}
          >
            Devices
          </button>
          {' '}and generate an agent token for their machine. Use the{' '}
          <Monitor size={12} color="#60A5FA" style={{ verticalAlign: 'middle' }} />{' '}
          button on each user row below to do this in one click.
        </p>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: 14, marginBottom: 28, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Users', value: stats.total, icon: <Users size={14} /> },
          { label: 'Active',      value: stats.active, icon: <UserCheck size={14} />, color: '#34D399' },
          { label: 'Admins',      value: stats.admins, icon: <Shield size={14} />, color: '#F59E0B' },
        ].map(s => (
          <div key={s.label} style={{
            background: '#111009', border: '1px solid rgba(42,40,32,0.9)', borderRadius: 10,
            padding: '14px 20px', display: 'flex', alignItems: 'center', gap: 12, minWidth: 140,
          }}>
            <span style={{ color: s.color || '#6B6357' }}>{s.icon}</span>
            <div>
              <p style={{ ...MONO, fontSize: 22, fontWeight: 700, color: s.color || '#F5F0E8', margin: 0, lineHeight: 1 }}>{s.value}</p>
              <p style={{ ...UI, fontSize: 11, color: '#6B6357', margin: 0, marginTop: 3 }}>{s.label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Tabs + Actions */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {['users', 'invites'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                ...UI, fontSize: 13, padding: '7px 16px', borderRadius: 7, cursor: 'pointer', border: 'none',
                background: tab === t ? 'rgba(245,158,11,0.12)' : 'transparent',
                color: tab === t ? '#F59E0B' : '#6B6357',
                outline: tab === t ? '1px solid rgba(245,158,11,0.25)' : 'none',
              }}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn variant="ghost" onClick={load} disabled={loading}><RefreshCw size={13} />Refresh</Btn>
          <Btn onClick={() => setShowCreate(true)}><Plus size={13} />New User</Btn>
        </div>
      </div>

      {/* Search */}
      {tab === 'users' && (
        <div style={{ marginBottom: 16 }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by email, username or role…"
            style={{ ...inputStyle, maxWidth: 360 }}
          />
        </div>
      )}

      {/* Users table */}
      {tab === 'users' && (
        <div style={{ border: '1px solid rgba(42,40,32,0.9)', borderRadius: 10, overflow: 'hidden' }}>
          {/* Table head */}
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 120px 90px 100px 160px 100px',
            padding: '10px 18px', background: '#0D0C0A',
            borderBottom: '1px solid rgba(42,40,32,0.9)',
          }}>
            {['User', 'Role', 'Status', '2FA', 'Actions'].map(h => (
              <span key={h} style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: '#4A443D' }}>{h.toUpperCase()}</span>
            ))}
            <span style={{ ...MONO, fontSize: 10, letterSpacing: '0.1em', color: '#4A443D' }}>MONITOR</span>
          </div>

          {loading ? (
            <div style={{ padding: '30px 18px', textAlign: 'center' }}>
              <p style={{ ...UI, color: '#6B6357', fontSize: 13 }}>Loading…</p>
            </div>
          ) : filtered.length === 0 ? (
            <div style={{ padding: '30px 18px', textAlign: 'center' }}>
              <p style={{ ...UI, color: '#6B6357', fontSize: 13 }}>No users found.</p>
            </div>
          ) : (
            filtered.map((u, i) => (
              <div
                key={u.id}
                style={{
                  display: 'grid', gridTemplateColumns: '1fr 120px 90px 100px 160px 100px',
                  padding: '13px 18px', alignItems: 'center',
                  borderBottom: i < filtered.length - 1 ? '1px solid rgba(42,40,32,0.5)' : 'none',
                  background: i % 2 === 0 ? 'transparent' : 'rgba(13,12,10,0.3)',
                }}
              >
                {/* User */}
                <div>
                  <p style={{ ...UI, fontSize: 13, color: '#F5F0E8', margin: 0, fontWeight: 500 }}>
                    {u.full_name || u.username}
                  </p>
                  <p style={{ ...MONO, fontSize: 11, color: '#6B6357', margin: 0 }}>{u.email}</p>
                  {u.must_change_password && (
                    <span style={{ ...MONO, fontSize: 9, color: '#F59E0B', letterSpacing: '0.08em' }}>MUST CHANGE PASSWORD</span>
                  )}
                </div>

                {/* Role */}
                <div><RoleBadge role={u.role} /></div>

                {/* Status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <StatusDot active={u.is_active} />
                  <span style={{ ...UI, fontSize: 12, color: u.is_active ? '#34D399' : '#EF4444' }}>
                    {u.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>

                {/* 2FA */}
                <div>
                  <span style={{ ...MONO, fontSize: 10, color: u.two_factor_enabled ? '#34D399' : '#4A443D' }}>
                    {u.two_factor_enabled ? 'ENABLED' : 'OFF'}
                  </span>
                </div>

                {/* Actions */}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={() => setEditUser(u)}
                    title="Edit role"
                    style={{ ...MONO, fontSize: 10, padding: '4px 10px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 5, color: '#F59E0B', cursor: 'pointer', letterSpacing: '0.05em' }}
                  >
                    EDIT
                  </button>
                  <button
                    onClick={() => setResetUser(u)}
                    title="Reset password"
                    style={{ ...MONO, fontSize: 10, padding: '4px 10px', background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.2)', borderRadius: 5, color: '#60A5FA', cursor: 'pointer', letterSpacing: '0.05em' }}
                  >
                    PW
                  </button>
                  <button
                    onClick={() => u.is_active ? setConfirmDeactivate(u) : toggleActive(u)}
                    title={u.is_active ? 'Deactivate' : 'Reactivate'}
                    style={{ ...MONO, fontSize: 10, padding: '4px 10px', background: u.is_active ? 'rgba(239,68,68,0.08)' : 'rgba(52,211,153,0.08)', border: `1px solid ${u.is_active ? 'rgba(239,68,68,0.2)' : 'rgba(52,211,153,0.2)'}`, borderRadius: 5, color: u.is_active ? '#EF4444' : '#34D399', cursor: 'pointer', letterSpacing: '0.05em' }}
                  >
                    {u.is_active ? 'OFF' : 'ON'}
                  </button>
                </div>

                {/* Monitor */}
                <div>
                  <button
                    onClick={() => navigate(`/devices?label=${encodeURIComponent(u.full_name || u.username)}`)}
                    title="Set up device monitoring for this user"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 5,
                      ...MONO, fontSize: 10, padding: '4px 10px', letterSpacing: '0.05em',
                      background: 'rgba(45,212,191,0.08)', border: '1px solid rgba(45,212,191,0.2)',
                      borderRadius: 5, color: '#2DD4BF', cursor: 'pointer',
                    }}
                  >
                    <Monitor size={11} /> DEVICE
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Invites tab */}
      <InvitesList show={tab === 'invites'} />

      {/* Confirm deactivate */}
      {confirmDeactivate && (
        <Modal title="Deactivate User" onClose={() => setConfirmDeactivate(null)}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 24 }}>
            <AlertTriangle size={18} color="#F59E0B" style={{ flexShrink: 0, marginTop: 2 }} />
            <p style={{ ...UI, fontSize: 14, color: '#F5F0E8', margin: 0 }}>
              Deactivate <strong>{confirmDeactivate.username}</strong>? They will be logged out immediately and cannot sign in.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <Btn variant="ghost" onClick={() => setConfirmDeactivate(null)}>Cancel</Btn>
            <Btn variant="danger" onClick={() => toggleActive(confirmDeactivate)}><UserX size={14} />Deactivate</Btn>
          </div>
        </Modal>
      )}

      {/* Modals */}
      {showCreate && <CreateUserModal onClose={() => setShowCreate(false)} onCreated={() => load()} />}
      {editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} onUpdated={() => load()} />}
      {resetUser && <ResetPwModal user={resetUser} onClose={() => setResetUser(null)} />}
    </div>
  );
}

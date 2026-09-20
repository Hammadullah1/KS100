import {describe,it,expect} from 'vitest';
import {freshness,validBundle} from '../src/data';
import type {Bundle,Forecast} from '../src/contracts.generated';
const f={p_up:.6,expires_at:'2026-09-22T11:00:00Z',update_due_at:'2026-09-21T14:00:00Z'} as Forecast;
const b={status:'ready',calendar_coverage_until:'2026-09-30T11:00:00Z',generated_at:'2026-09-18T14:00:00Z',update_due_at:f.update_due_at} as Bundle;
describe('client clock gates',()=>{
 it('expires cached forecasts even if scheduler never wakes',()=>expect(freshness(b,f,Date.parse('2026-09-22T12:00:00Z')).state).toBe('historical'));
 it('marks missed update independently of target expiry',()=>expect(freshness(b,f,Date.parse('2026-09-21T15:00:00Z')).state).toBe('delayed'));
 it('refuses freshness without calendar coverage',()=>expect(freshness({...b,calendar_coverage_until:null},f,Date.parse('2026-09-19T12:00:00Z')).state).toBe('unknown'));
 it('does not substitute 50/50 for missing model',()=>expect(freshness(b,undefined,Date.now()).state).toBe('unavailable'));
 it('rejects malformed production bundle',()=>expect(validBundle({...b,mode:'fixture'})).toBe(false));
});

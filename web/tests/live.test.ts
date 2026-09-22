import {afterEach,expect,it,vi} from 'vitest';
import {loadLive,liveState,validLive,type LiveFeed} from '../src/live';
const estimate={horizon:1 as const,reference_session:'2026-09-18',issued_at:'2026-09-20T06:00:00Z',update_due_at:'2026-09-21T14:45:00Z',p_up:.55,p_not_up:.45,baseline_up:.5,model_version:'research-test',reference_hash:'hash',outcome:null};
const feed:LiveFeed={schema_version:'research-live-v1',mode:'experimental',instrument:'KSE100',generated_at:'2026-09-20T06:00:00Z',reference_session:'2026-09-18',source_url:'https://dps.psx.com.pk/',model_name:'research',validation:'No demonstrated forecasting advantage',calendar_status:'unverified',forecast_basis:'recorded observations',forecasts:[estimate,{...estimate,horizon:5}],history:[estimate,{...estimate,horizon:5}]};
afterEach(()=>{vi.unstubAllGlobals();localStorage.clear();});
it('rejects invalid probabilities and unexpected evidence mode',()=>{
 expect(validLive(feed)).toBe(true);
 expect(validLive({...feed,mode:'validated'})).toBe(false);
 expect(validLive({...feed,forecasts:[{...estimate,p_up:1.5},{...estimate,horizon:5}]})).toBe(false);
});
it('never treats an overdue or cached estimate as current',()=>{
 expect(liveState({feed,cached:false,error:null},Date.parse('2026-09-22'))).toMatch(/overdue/);
 expect(liveState({feed,cached:true,error:'Network failed'},Date.parse('2026-09-20T07:00:00Z'))).toMatch(/saved estimate/);
});
it('falls back to validated cache on network failure with an explicit warning',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,text:async()=>JSON.stringify(feed)}));
 expect((await loadLive()).cached).toBe(false);
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(Error('Network failed')));
 const result=await loadLive();expect(result.cached).toBe(true);expect(result.error).toBe('Network failed');
});

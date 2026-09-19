import assert from 'node:assert/strict';
import test from 'node:test';
import {parseIcs} from '../lib/ics';
import {mergeBusy} from '../lib/calendar';
import {googleBusy, validGoogleToken, GOOGLE_SCOPE} from '../lib/google-calendar';
const bounds = {start_time:'2026-09-19T16:00:00Z', end_time:'2026-09-19T20:00:00Z'};
const cal = (...events: string[]) => `BEGIN:VCALENDAR\r\nVERSION:2.0\r\n${events.map(e=>`BEGIN:VEVENT\r\n${e.replaceAll('\n','\r\n')}\r\nEND:VEVENT`).join('\r\n')}\r\nEND:VCALENDAR`;
const event = 'UID:class\nDTSTART;TZID=America/New_York:20260919T130000\nDTEND;TZID=America/New_York:20260919T140000';
test('IANA timezone, titles discarded, UTC output',()=>{
 assert.deepEqual(parseIcs(cal(event+'\nSUMMARY:Secret class'),bounds),[{start_time:'2026-09-19T17:00:00.000Z',end_time:'2026-09-19T18:00:00.000Z'}]);
});
test('floating times default Eastern and UTC stays UTC',()=>{
 assert.equal(parseIcs(cal(event.replaceAll(';TZID=America/New_York','')),bounds)[0].start_time,'2026-09-19T17:00:00.000Z');
 assert.equal(parseIcs(cal('UID:utc\nDTSTART:20260919T170000Z\nDURATION:PT1H'),bounds)[0].end_time,'2026-09-19T18:00:00.000Z');
});
test('weekly recurrence, EXDATE, and RDATE',()=>{
 const weekly=event.replaceAll('20260919','20260912')+'\nRRULE:FREQ=WEEKLY;COUNT=3';
 assert.equal(parseIcs(cal(weekly),bounds).length,1);
 assert.equal(parseIcs(cal(weekly+'\nEXDATE;TZID=America/New_York:20260919T130000'),bounds).length,0);
 assert.equal(parseIcs(cal(event.replaceAll('20260919','20260912')+'\nRDATE;TZID=America/New_York:20260919T130000'),bounds).length,1);
});
test('canceled exception and moved exception replace original',()=>{
 const base=event+'\nRRULE:FREQ=DAILY;COUNT=2';
 const exception='UID:class\nRECURRENCE-ID;TZID=America/New_York:20260919T130000';
 assert.equal(parseIcs(cal(base,exception+'\nSTATUS:CANCELLED'),bounds).length,0);
 const moved=exception+'\nDTSTART;TZID=America/New_York:20260919T150000\nDTEND;TZID=America/New_York:20260919T160000';
 assert.deepEqual(parseIcs(cal(base,moved),bounds),[{start_time:'2026-09-19T19:00:00.000Z',end_time:'2026-09-19T20:00:00.000Z'}]);
});
test('moved exception originally after horizon still included',()=>{
 const base=event.replaceAll('20260919','20260920')+'\nRRULE:FREQ=DAILY;COUNT=2';
 const moved=event+'\nRECURRENCE-ID;TZID=America/New_York:20260920T130000';
 assert.equal(parseIcs(cal(base,moved),bounds).length,1);
});
test('all-day exclusive end and overnight clipped to search',()=>{
 assert.deepEqual(parseIcs(cal('UID:day\nDTSTART;VALUE=DATE:20260919\nDTEND;VALUE=DATE:20260920'),bounds),[{start_time:'2026-09-19T16:00:00.000Z',end_time:'2026-09-19T20:00:00.000Z'}]);
 assert.equal(parseIcs(cal('UID:day\nDTSTART;VALUE=DATE:20260918\nDTEND;VALUE=DATE:20260919'),bounds).length,0);
 assert.equal(parseIcs(cal('UID:night\nDTSTART:20260918T230000\nDTEND:20260919T130000'),bounds)[0].end_time,'2026-09-19T17:00:00.000Z');
});
test('transparent and canceled events skipped',()=>{
 assert.deepEqual(parseIcs(cal(event+'\nTRANSP:TRANSPARENT'),bounds),[]);
 assert.deepEqual(parseIcs(cal(event+'\nSTATUS:CANCELLED'),bounds),[]);
});
test('recurrence preserves local time across DST',()=>{
 const dst={start_time:'2026-11-01T16:00:00Z',end_time:'2026-11-01T20:00:00Z'};
 const base=event.replaceAll('20260919','20261025')+'\nRRULE:FREQ=WEEKLY;COUNT=2';
 assert.equal(parseIcs(cal(base),dst)[0].start_time,'2026-11-01T18:00:00.000Z');
});
test('malformed, oversized, unknown timezone, and conflicting revisions fail',()=>{
 assert.throws(()=>parseIcs('no calendar',bounds));
 assert.throws(()=>parseIcs('x'.repeat(1024*1024+1),bounds),/1 MB/);
 assert.throws(()=>parseIcs(cal(event.replaceAll('America/New_York','Unknown/Zone')),bounds),/time zone/);
 assert.throws(()=>parseIcs(cal(event,event),bounds),/duplicate/);
});
test('overlap, adjacency, clipping and duplicates merge without losing time',()=>{
 assert.deepEqual(mergeBusy([{start_time:'2026-09-19T15:00:00Z',end_time:'2026-09-19T17:00:00Z'},{start_time:'2026-09-19T17:00:00Z',end_time:'2026-09-19T18:00:00Z'}],bounds),[{start_time:'2026-09-19T16:00:00.000Z',end_time:'2026-09-19T18:00:00.000Z'}]);
});
test('Google request uses primary freebusy only and validates scope',async()=>{
 const fake: typeof fetch=async(url,options)=>{
  assert.equal(url,'https://www.googleapis.com/calendar/v3/freeBusy');
  assert.deepEqual(JSON.parse(options!.body as string).items,[{id:'primary'}]);
  assert.equal((options!.headers as Record<string,string>).Authorization,'Bearer test-only');
  return Response.json({timeMin:bounds.start_time,timeMax:bounds.end_time,calendars:{primary:{busy:[{start:'2026-09-19T17:00:00Z',end:'2026-09-19T18:00:00Z'}]}}});
 };
 assert.equal((await googleBusy('test-only',bounds,fake)).length,1);
 assert.ok(validGoogleToken({access_token:'test-only',expires_in:3600,scope:GOOGLE_SCOPE}));
 assert.ok(!validGoogleToken({access_token:'test-only',expires_in:3600,scope:'unrelated'}));
});
test('Google failures, missing or partial data never become free time',async()=>{
 for(const result of [{status:401}, {status:403}, {status:200,data:{calendars:{primary:{errors:[{reason:'notFound'}]}}}}, {status:200,data:{calendars:{primary:{busy:[]}}}}]){
  await assert.rejects(googleBusy('test-only',bounds,async()=>Response.json(result.data||{}, {status:result.status})));
 }
});
test('VTIMEZONE definitions resolve custom export TZIDs',()=>{
 const zone=`BEGIN:VTIMEZONE\r\nTZID:CampusZone\r\nBEGIN:STANDARD\r\nDTSTART:19700101T000000\r\nTZOFFSETFROM:-0400\r\nTZOFFSETTO:-0400\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n`;
 const text=cal(event.replaceAll('America/New_York','CampusZone')).replace('BEGIN:VEVENT',zone+'BEGIN:VEVENT');
 assert.equal(parseIcs(text,bounds)[0].start_time,'2026-09-19T17:00:00.000Z');
});
test('spring gap fails and fall overlap chooses first occurrence',()=>{
 const start='UID:dst\nDTSTART;TZID=America/New_York:20260308T023000\nDURATION:PT1H';
 assert.throws(()=>parseIcs(cal(start),{start_time:'2026-03-08T05:00:00Z',end_time:'2026-03-08T10:00:00Z'}),/nonexistent/);
 assert.equal(parseIcs(cal(start.replaceAll('20260308T023000','20261101T013000')),{start_time:'2026-11-01T04:00:00Z',end_time:'2026-11-01T09:00:00Z'})[0].start_time,'2026-11-01T05:30:00.000Z');
});
test('calendar default timezone and multi-day events',()=>{
 const text=cal('UID:days\nDTSTART;VALUE=DATE:20260919\nDTEND;VALUE=DATE:20260921').replace('VERSION:2.0','VERSION:2.0\r\nX-WR-TIMEZONE:Europe/London');
 const range={start_time:'2026-09-18T21:00:00Z',end_time:'2026-09-19T01:00:00Z'};
 assert.equal(parseIcs(text,range)[0].start_time,'2026-09-18T23:00:00.000Z');
});
test('more than 50 disjoint busy periods fails instead of truncating',()=>{
 const start=Date.parse(bounds.start_time);
 const rows=Array.from({length:51},(_,n)=>({start_time:new Date(start+n*120000).toISOString(),end_time:new Date(start+n*120000+60000).toISOString()}));
 assert.throws(()=>mergeBusy(rows,bounds),/Too many/);
});
test('opaque exception can block a transparent recurring series',()=>{
 const base=event+'\nTRANSP:TRANSPARENT\nRRULE:FREQ=DAILY;COUNT=2';
 const override=event+'\nRECURRENCE-ID;TZID=America/New_York:20260919T130000\nTRANSP:OPAQUE';
 assert.equal(parseIcs(cal(base,override),bounds).length,1);
});

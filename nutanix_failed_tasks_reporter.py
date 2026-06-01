import http.client, json, ssl

NTNX_PRISMCENTRAL_IP = "YOUR_IP:9440"
PC_TOKEN = "YOUR GENERATED TOKEN FROM nutanix_auth.py"

def api_request(method, url, payload=None):
    context = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection(NTNX_PRISMCENTRAL_IP, context=context)
    headers = {"Accept": "application/json", "Authorization": PC_TOKEN, "Content-Type": "application/json"}
    body = json.dumps(payload) if isinstance(payload, dict) else payload
    conn.request(method, url, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8")
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        data = {"raw": raw}
    if res.status >= 400:
        raise RuntimeError(f"API error {res.status} on {url}: {data}")
    return data

def list_entities(kind, endpoint):
    offset = 0
    out = []
    while True:
        data = api_request("POST", endpoint, {"kind": kind, "length": 100, "offset": offset})
        entities = data.get("entities", [])
        if not entities:
            break
        out.extend(entities)
        total = data.get("metadata", {}).get("total_matches")
        offset += 100
        if total is not None and offset >= total:
            break
    return out

import argparse
from datetime import datetime, timedelta, timezone

def parse_dt(v):
    if not v: return None
    if isinstance(v,(int,float)):
        n=float(v); return datetime.fromtimestamp(n/1000000 if n>10000000000000 else n/1000 if n>10000000000 else n, tz=timezone.utc)
    if isinstance(v,str):
        try:
            d=datetime.fromisoformat(v.strip().replace("Z","+00:00")); return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError: return None
    return None

def first_dt(task, names):
    sources=[task, task.get("status") if isinstance(task.get("status"),dict) else {}, task.get("metadata") if isinstance(task.get("metadata"),dict) else {}]
    for src in sources:
        for name in names:
            d=parse_dt(src.get(name))
            if d: return d
    return None

def task_info(t):
    s=t.get("status") if isinstance(t.get("status"),dict) else {}
    m=t.get("metadata") if isinstance(t.get("metadata"),dict) else {}
    status=t.get("status") if isinstance(t.get("status"),str) else s.get("state") or s.get("status") or "UNKNOWN"
    start=first_dt(t,["start_time","startTime","created_time","creation_time","createdAt"]); end=first_dt(t,["completion_time","completionTime","last_update_time","lastUpdateTime"])
    return {"uuid":m.get("uuid") or t.get("uuid") or t.get("task_uuid"),"status":str(status).upper(),"operation":s.get("operation_type") or t.get("operation_type") or t.get("name"),"started_at":start.isoformat() if start else None,"completed_at":end.isoformat() if end else None,"running_minutes":round((datetime.now(timezone.utc)-start).total_seconds()/60,2) if start and not end else None,"error":s.get("error_detail") or t.get("error_detail") or t.get("message")}

def main():
    p=argparse.ArgumentParser(description="Report failed, aborted, or long-running Nutanix Prism Central tasks.")
    p.add_argument("--status",action="append",default=None); p.add_argument("--last-hours",type=int,default=24); p.add_argument("--long-running-minutes",type=int); p.add_argument("--max-pages",type=int,default=20); p.add_argument("--json-file")
    a=p.parse_args(); statuses={x.upper() for x in (a.status or ["FAILED","ABORTED"])}; rows=[]; since=datetime.now(timezone.utc)-timedelta(hours=a.last_hours)
    for task in list_entities("task","/api/nutanix/v3/tasks/list")[:a.max_pages*100]:
        info=task_info(task); d=parse_dt(info.get("started_at")) or parse_dt(info.get("completed_at"))
        if info["status"] not in statuses: continue
        if d and d<since: continue
        if a.long_running_minutes is not None and (info.get("running_minutes") is None or info["running_minutes"]<a.long_running_minutes): continue
        rows.append(info)
    print(json.dumps(rows,indent=2,ensure_ascii=False))
    if a.json_file: open(a.json_file,"w",encoding="utf-8").write(json.dumps(rows,indent=2,ensure_ascii=False))
    if rows: raise SystemExit(1)
if __name__=="__main__": main()

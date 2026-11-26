import requests, time, json, sys
B="http://localhost:8765/api"; V="/mnt/user-data/attachments/5a7f8a2c-0812-519a-a0a8-d5ec196d1b51/be26af24-test_short_clip.mp4"
def chk(name, r, ok=(200,)):
    print(("PASS " if r.status_code in ok else "FAIL ")+name, r.status_code, r.text[:140].replace("\n"," ") if r.status_code not in ok else "")
    return r
chk("health", requests.get(B+"/health")); chk("capabilities", requests.get(B+"/capabilities"))
p=chk("create project", requests.post(B+"/projects", json={"name":"walk","description":"d"})).json(); pid=p["id"]
chk("create project empty name rejected", requests.post(B+"/projects", json={"name":""}), ok=(400,422))
chk("list projects", requests.get(B+"/projects")); chk("get project", requests.get(f"{B}/projects/{pid}"))
chk("get missing project 404", requests.get(B+"/projects/nope"), ok=(404,))
chk("samples list", requests.get(B+"/projects/samples/list"))
chk("results before run", requests.get(f"{B}/projects/{pid}/results"), ok=(200,404))
chk("upload non-video rejected", requests.post(f"{B}/projects/{pid}/video", files={"file":("a.txt",b"hello")}), ok=(400,415,422))
chk("upload video", requests.post(f"{B}/projects/{pid}/video", files={"file":("clip.mp4",open(V,"rb"),"video/mp4")}))
chk("start with bad preset rejected", requests.post(f"{B}/projects/{pid}/reconstruction", json={"quality_preset":"ultra"}), ok=(400,422))
r=chk("start reconstruction", requests.post(f"{B}/projects/{pid}/reconstruction", json={"quality_preset":"fast","sampling_fps":4,"max_frames":30,"gpu_mode":"cpu","matching_strategy":"exhaustive"})); jid=r.json().get("job_id")
chk("job status", requests.get(f"{B}/jobs/{jid}")); chk("project job", requests.get(f"{B}/projects/{pid}/job"))
chk("second start while running rejected", requests.post(f"{B}/projects/{pid}/reconstruction", json={}), ok=(400,409))
t=time.time(); last=None
while time.time()-t<1500:
    j=requests.get(f"{B}/jobs/{jid}").json(); st=j.get("status")
    cur=[(s["stage_id"],s["status"]) for s in j.get("stages",[]) if s["status"] in("running","failed")]
    if cur!=last: print(f"  [{int(time.time()-t)}s] {st} {cur}"); last=cur
    if st in("completed","failed","cancelled"): break
    time.sleep(5)
print("FINAL", st, j.get("error"))
for s in j.get("stages",[]): print("  stage", s["stage_id"], s["status"], (s.get("error") or "")[:150])
chk("results", requests.get(f"{B}/projects/{pid}/results")); 
res=requests.get(f"{B}/projects/{pid}/results").json(); print(json.dumps(res)[:1500])
chk("frames", requests.get(f"{B}/projects/{pid}/frames"))
for f in (res.get("files") or {}).values():
    u=f.get("download_url") or f.get("url")
    if u: 
        rr=requests.get("http://localhost:8765"+u if u.startswith("/") else u); print("  download", f.get("filename"), rr.status_code, len(rr.content))
chk("file traversal blocked", requests.get(f"{B}/projects/{pid}/files/..%2F..%2Fconfig.py"), ok=(400,403,404))
chk("events stream", requests.get(f"{B}/jobs/{jid}/events", stream=True, timeout=5))
chk("cancel finished job", requests.post(f"{B}/jobs/{jid}/cancel"), ok=(200,400,409))
chk("delete project", requests.delete(f"{B}/projects/{pid}")); chk("deleted project gone", requests.get(f"{B}/projects/{pid}"), ok=(404,))

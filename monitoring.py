"""
app/routes/monitoring.py  -- Task 3: Monitoring & Dashboard Endpoints
"""
import os
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, func

from app.core.database import get_db
from app.core.cache import get_cache_stats, flush_cache, check_redis_connection
from app.core.config import settings
from app.core.logger import logger
from app.core.security import require_admin
from app.models.book import Book
from app.models.user import User
from app.models.borrow_record import BorrowRecord, BorrowStatus

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get("/stats", summary="Full system statistics (Admin only)", dependencies=[Depends(require_admin)])
def get_system_stats(db: Session = Depends(get_db)):
    total_books = db.query(func.count(Book.id)).scalar()
    available_books = db.query(func.count(Book.id)).filter(Book.available_copies > 0).scalar()
    total_users = db.query(func.count(User.id)).scalar()
    active_borrows = db.query(func.count(BorrowRecord.id)).filter(BorrowRecord.status == BorrowStatus.active).scalar()
    overdue_borrows = db.query(func.count(BorrowRecord.id)).filter(BorrowRecord.status == BorrowStatus.overdue).scalar()
    total_borrows = db.query(func.count(BorrowRecord.id)).scalar()

    cache = get_cache_stats()

    redis_latency_ms = None
    if check_redis_connection():
        from app.core.cache import get_redis
        client = get_redis()
        try:
            t0 = time.perf_counter()
            client.ping()
            redis_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        except Exception:
            pass

    db_latency_ms = None
    try:
        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
    except Exception:
        pass

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "library": {
            "total_books": total_books,
            "available_books": available_books,
            "total_users": total_users,
            "active_borrows": active_borrows,
            "overdue_borrows": overdue_borrows,
            "total_borrow_records": total_borrows,
        },
        "cache": cache,
        "infrastructure": {
            "database_latency_ms": db_latency_ms,
            "redis_latency_ms": redis_latency_ms,
            "redis_available": check_redis_connection(),
        },
    }


@router.get("/cache/stats", summary="Redis cache statistics", dependencies=[Depends(require_admin)])
def get_cache_statistics():
    return get_cache_stats()


@router.post("/cache/flush", summary="Flush cache (Admin only)", dependencies=[Depends(require_admin)])
def flush_all_cache(pattern: str = Query(default="*", description="Key pattern to flush")):
    count = flush_cache(pattern)
    logger.warning(f"Cache flushed by admin: pattern='{pattern}' keys_removed={count}")
    return {"message": f"Cache flushed for pattern '{pattern}'", "keys_removed": count if count >= 0 else "all"}


@router.get("/logs/recent", summary="View recent log lines (Admin only)", dependencies=[Depends(require_admin)])
def get_recent_logs(
    lines: int = Query(default=50, ge=1, le=500),
    level: str = Query(default="INFO"),
):
    log_file = settings.LOG_FILE
    if not os.path.exists(log_file):
        return {"lines": [], "message": "Log file not found yet"}

    import json as json_lib
    result = []
    level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
    min_level = level_order.get(level.upper(), 1)

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()

        for raw_line in reversed(all_lines):
            if len(result) >= lines:
                break
            try:
                entry = json_lib.loads(raw_line.strip())
                record = entry.get("record", {})
                entry_level = record.get("level", {}).get("name", "INFO")
                if level_order.get(entry_level, 0) >= min_level:
                    result.append({
                        "time": record.get("time", {}).get("repr", ""),
                        "level": entry_level,
                        "module": record.get("name", ""),
                        "message": record.get("message", ""),
                    })
            except Exception:
                result.append({"raw": raw_line.strip()})

        return {"total_lines_scanned": len(all_lines), "returned": len(result), "entries": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not read log file: {e}")


@router.get("/health/detailed", summary="Deep health check with latency probes")
def detailed_health(db: Session = Depends(get_db)):
    results = {}

    try:
        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        results["database"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
    except Exception as e:
        results["database"] = {"status": "error", "detail": str(e)}

    try:
        from app.core.cache import get_redis
        client = get_redis()
        if client:
            t0 = time.perf_counter()
            client.ping()
            results["redis"] = {"status": "ok", "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        else:
            results["redis"] = {"status": "unavailable"}
    except Exception as e:
        results["redis"] = {"status": "error", "detail": str(e)}

    overall = "healthy" if all(v.get("status") == "ok" for v in results.values()) else "degraded"
    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "dependencies": results,
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Library Monitoring Dashboard</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
    header{background:#1e293b;padding:20px 32px;border-bottom:1px solid #334155;display:flex;align-items:center;justify-content:space-between}
    header h1{font-size:1.4rem;font-weight:700;color:#f8fafc}
    header h1 span{color:#38bdf8}
    .badge{background:#064e3b;color:#6ee7b7;border-radius:999px;padding:4px 12px;font-size:.75rem;font-weight:600}
    .badge.red{background:#450a0a;color:#fca5a5}
    main{max-width:1200px;margin:32px auto;padding:0 24px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:28px}
    .card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:20px 24px}
    .card .label{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
    .card .value{font-size:2rem;font-weight:800;color:#f8fafc}
    .card .sub{font-size:.8rem;color:#64748b;margin-top:4px}
    .card.blue .value{color:#38bdf8}.card.green .value{color:#4ade80}
    .card.yellow .value{color:#facc15}.card.red .value{color:#f87171}.card.purple .value{color:#a78bfa}
    .section-title{font-size:.85rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.1em;margin:20px 0 12px}
    .infra{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
    .infra-card{background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px 20px}
    .infra-card .title{font-size:.85rem;font-weight:600;color:#cbd5e1;margin-bottom:12px}
    .row{display:flex;justify-content:space-between;align-items:center;margin:6px 0;font-size:.82rem;color:#94a3b8}
    .row span:last-child{color:#e2e8f0;font-weight:500}
    .dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
    .dg{background:#4ade80;box-shadow:0 0 6px #4ade80}.dr{background:#f87171}.dy{background:#facc15}
    .pb{background:#0f172a;border-radius:999px;height:8px;margin-top:4px;overflow:hidden}
    .pf{height:100%;border-radius:999px;background:linear-gradient(90deg,#38bdf8,#818cf8);transition:width .5s}
    .err{background:#450a0a;border:1px solid #7f1d1d;color:#fca5a5;border-radius:8px;padding:12px;font-size:.85rem;display:none;margin-bottom:16px}
    .ts{font-size:.72rem;color:#475569;text-align:right;margin-top:20px}
    a{color:#38bdf8;text-decoration:none}a:hover{text-decoration:underline}
  </style>
</head>
<body>
<header>
  <h1>📚 <span>Library</span> Monitoring</h1>
  <div id="badge" class="badge">● Loading…</div>
</header>
<main>
  <div class="err" id="err"></div>
  <div class="section-title">Library Overview</div>
  <div class="grid">
    <div class="card blue"><div class="label">Total Books</div><div class="value" id="tb">—</div><div class="sub" id="ab">Available: —</div></div>
    <div class="card green"><div class="label">Registered Users</div><div class="value" id="tu">—</div></div>
    <div class="card yellow"><div class="label">Active Borrows</div><div class="value" id="ab2">—</div></div>
    <div class="card red"><div class="label">Overdue</div><div class="value" id="ob">—</div></div>
    <div class="card purple"><div class="label">Total Records</div><div class="value" id="tr">—</div></div>
  </div>
  <div class="section-title">Cache Performance</div>
  <div class="grid">
    <div class="card green"><div class="label">Cache Hits</div><div class="value" id="ch">—</div></div>
    <div class="card red"><div class="label">Cache Misses</div><div class="value" id="cm">—</div></div>
    <div class="card blue"><div class="label">Hit Rate</div><div class="value" id="hr">—</div><div class="pb"><div class="pf" id="hrb" style="width:0%"></div></div></div>
    <div class="card"><div class="label">Memory Used</div><div class="value" id="mu" style="font-size:1.3rem">—</div><div class="sub" id="ck">Keys: —</div></div>
  </div>
  <div class="section-title">Infrastructure</div>
  <div class="infra">
    <div class="infra-card"><div class="title">🗄️ Database</div>
      <div class="row"><span>Status</span><span id="dbs">—</span></div>
      <div class="row"><span>Latency</span><span id="dbl">—</span></div>
    </div>
    <div class="infra-card"><div class="title">⚡ Redis Cache</div>
      <div class="row"><span>Status</span><span id="rs">—</span></div>
      <div class="row"><span>Latency</span><span id="rl">—</span></div>
    </div>
    <div class="infra-card"><div class="title">🔗 Quick Links</div>
      <div class="row"><span><a href="/docs">Swagger UI</a></span></div>
      <div class="row"><span><a href="/redoc">ReDoc</a></span></div>
      <div class="row"><span><a href="http://localhost:9090" target="_blank">Prometheus ↗</a></span></div>
      <div class="row"><span><a href="http://localhost:3000" target="_blank">Grafana ↗</a></span></div>
    </div>
  </div>
  <div class="ts" id="ts">Refreshing every 10s…</div>
</main>
<script>
async function load(){
  try{
    const r=await fetch('/api/v1/monitoring/stats');
    if(!r.ok)throw new Error('HTTP '+r.status+' — are you logged in as admin?');
    const d=await r.json();
    const L=d.library;
    document.getElementById('tb').textContent=L.total_books;
    document.getElementById('ab').textContent='Available: '+L.available_books;
    document.getElementById('tu').textContent=L.total_users;
    document.getElementById('ab2').textContent=L.active_borrows;
    document.getElementById('ob').textContent=L.overdue_borrows;
    document.getElementById('tr').textContent=L.total_borrow_records;
    const c=d.cache;
    if(c.available){
      document.getElementById('ch').textContent=c.hits.toLocaleString();
      document.getElementById('cm').textContent=c.misses.toLocaleString();
      document.getElementById('hr').textContent=c.hit_rate_percent+'%';
      document.getElementById('hrb').style.width=c.hit_rate_percent+'%';
      document.getElementById('mu').textContent=c.memory_used;
      const k=c.key_counts;
      document.getElementById('ck').textContent='Books:'+k.books+' Users:'+k.users+' BL:'+k.blacklist;
    } else {
      ['ch','cm','hr','mu'].forEach(id=>document.getElementById(id).textContent='N/A');
    }
    const i=d.infrastructure;
    const dbOk=i.database_latency_ms!==null;
    document.getElementById('dbs').innerHTML=dbOk?'<span class="dot dg"></span>OK':'<span class="dot dr"></span>Error';
    document.getElementById('dbl').textContent=dbOk?i.database_latency_ms+'ms':'—';
    document.getElementById('rs').innerHTML=i.redis_available?'<span class="dot dg"></span>OK':'<span class="dot dy"></span>Unavailable';
    document.getElementById('rl').textContent=i.redis_latency_ms?i.redis_latency_ms+'ms':'—';
    document.getElementById('badge').textContent='● Healthy';
    document.getElementById('badge').className='badge';
    document.getElementById('err').style.display='none';
    document.getElementById('ts').textContent='Last updated: '+new Date().toLocaleTimeString();
  }catch(e){
    document.getElementById('badge').textContent='● Error';
    document.getElementById('badge').className='badge red';
    const el=document.getElementById('err');
    el.style.display='block';
    el.textContent='Could not fetch stats: '+e.message;
  }
}
load();setInterval(load,10000);
</script>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse, summary="Built-in monitoring dashboard (Admin only)")
def monitoring_dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

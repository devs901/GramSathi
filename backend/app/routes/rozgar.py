"""Rozgar: local jobs, worker profiles, applications and moderation."""
from __future__ import annotations
import json, re
from pydantic import BaseModel, Field
from .. import db as dbm
from ..http import ApiError, endpoint

class ProfileIn(BaseModel):
    profile_type: str = Field(default='worker', pattern='^(worker|employer)$')
    headline: str = Field(default='', max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=30)
    experience_years: float = Field(default=0, ge=0, le=60)
    education: str = Field(default='', max_length=160)
    location: str = Field(default='', max_length=120)
    bio: str = Field(default='', max_length=1200)
    phone_public: bool = False

class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    company: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=20, max_length=5000)
    skills: list[str] = Field(default_factory=list, max_length=30)
    location: str = Field(min_length=2, max_length=120)
    job_type: str = Field(default='Full-time', max_length=40)
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)

class ApplyIn(BaseModel):
    cover_note: str = Field(default='', max_length=1500)

class StatusIn(BaseModel):
    status: str = Field(pattern='^(shortlisted|rejected|hired)$')

class ModerateIn(BaseModel):
    status: str = Field(pattern='^(published|rejected)$')

SCAM_TERMS = ['registration fee','pay security deposit','processing fee','guaranteed income','send otp','whatsapp only','crypto investment','pay to get job']
def scam_check(text: str):
    t=text.lower(); norm=' '.join(re.sub(r'[^a-z0-9]+',' ',t).split()); flags=[x for x in SCAM_TERMS if x in norm]
    if re.search(r'\b\d{10}\b', t) and ('whatsapp' in t or 'telegram' in t): flags.append('unverified personal contact')
    return min(100, len(flags)*35), flags

def match_profile(profile, job):
    raw_p=(profile or {}).get('skills', [])
    if isinstance(raw_p, str): raw_p=dbm.loads(raw_p, [])
    raw_j=job.get('skills', [])
    if isinstance(raw_j, str): raw_j=dbm.loads(raw_j, [])
    p={x.strip().lower() for x in raw_p}
    j={x.strip().lower() for x in raw_j}
    overlap=sorted(p & j)
    score=round(100*len(overlap)/max(1,len(j))) if j else 0
    if profile and profile.get('location','').lower() == job.get('location','').lower(): score=min(100,score+10)
    reason=('Matching skills: '+', '.join(overlap)) if overlap else 'Add relevant skills to your profile to improve this match.'
    return score, reason

@endpoint()
def get_profile(ctx):
    p=dbm.row(ctx.db,'SELECT * FROM rozgar_profiles WHERE user_id=?',(ctx.user['id'],))
    if p: p['skills']=dbm.loads(p['skills'],[])
    return {'profile':p}

@endpoint(body=ProfileIn)
def save_profile(ctx,p):
    dbm.execute(ctx.db,'''INSERT INTO rozgar_profiles(user_id,profile_type,headline,skills,experience_years,education,location,bio,phone_public,updated_at)
    VALUES(?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) ON CONFLICT(user_id) DO UPDATE SET profile_type=excluded.profile_type,headline=excluded.headline,skills=excluded.skills,experience_years=excluded.experience_years,education=excluded.education,location=excluded.location,bio=excluded.bio,phone_public=excluded.phone_public,updated_at=excluded.updated_at''',
    (ctx.user['id'],p.profile_type,p.headline,json.dumps(p.skills),p.experience_years,p.education,p.location,p.bio,int(p.phone_public)))
    return {'message':'Rozgar profile saved','profile_type':p.profile_type}

@endpoint()
def list_jobs(ctx):
    q=(ctx.request.query_params.get('q') or '').strip()[:100]
    loc=(ctx.request.query_params.get('location') or '').strip()[:100]
    rows=dbm.rows(ctx.db,"SELECT j.*,u.name employer_name FROM rozgar_jobs j JOIN users u ON u.id=j.employer_id WHERE j.status='published' AND (?='' OR j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?) AND (?='' OR j.location LIKE ?) ORDER BY j.created_at DESC LIMIT 100",(q,f'%{q}%',f'%{q}%',f'%{q}%',loc,f'%{loc}%'))
    for j in rows: j['skills']=dbm.loads(j['skills'],[]); j['scam_flags']=dbm.loads(j['scam_flags'],[])
    profile=dbm.row(ctx.db,'SELECT * FROM rozgar_profiles WHERE user_id=?',(ctx.user['id'],))
    if profile: profile['skills']=dbm.loads(profile['skills'],[])
    for j in rows:
        j['match_score'],j['match_reason']=match_profile(profile,j)
        j['applied']=bool(dbm.scalar(ctx.db,'SELECT 1 FROM rozgar_applications WHERE job_id=? AND worker_id=?',(j['id'],ctx.user['id'])))
    return {'items':rows}

@endpoint(body=JobIn)
def create_job(ctx,p):
    if p.salary_min is not None and p.salary_max is not None and p.salary_max < p.salary_min: raise ApiError(422,'Maximum salary must be greater than minimum salary')
    score,flags=scam_check(' '.join([p.title,p.company,p.description,*p.skills]))
    status='pending' if score>=35 else 'published'
    jid=dbm.execute(ctx.db,'INSERT INTO rozgar_jobs(employer_id,title,company,description,skills,location,job_type,salary_min,salary_max,status,scam_score,scam_flags) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ctx.user['id'],p.title,p.company,p.description,json.dumps(p.skills),p.location,p.job_type,p.salary_min,p.salary_max,status,score,json.dumps(flags)))
    dbm.audit(ctx.db,ctx.user['id'],'create','rozgar_job',jid,'Rozgar job post '+status)
    return {'id':jid,'status':status,'scam_score':score,'flags':flags,'message':'Job submitted for admin review' if status=='pending' else 'Job published'}

@endpoint(body=ApplyIn)
def apply(ctx,p):
    jid=int(ctx.request.path_params['id'])
    job=dbm.row(ctx.db,"SELECT * FROM rozgar_jobs WHERE id=? AND status='published'",(jid,))
    if not job: raise ApiError(404,'Job not found or not published')
    if job['employer_id']==ctx.user['id']: raise ApiError(403,'You cannot apply to your own job')
    if dbm.scalar(ctx.db,'SELECT 1 FROM rozgar_applications WHERE job_id=? AND worker_id=?',(jid,ctx.user['id'])): raise ApiError(409,'You have already applied to this job')
    profile=dbm.row(ctx.db,'SELECT * FROM rozgar_profiles WHERE user_id=?',(ctx.user['id'],))
    if profile: profile['skills']=dbm.loads(profile['skills'],[])
    score,reason=match_profile(profile,job)
    aid=dbm.execute(ctx.db,'INSERT INTO rozgar_applications(job_id,worker_id,cover_note,match_score,match_reason) VALUES(?,?,?,?,?)',(jid,ctx.user['id'],p.cover_note,score,reason))
    return {'id':aid,'match_score':score,'match_reason':reason,'message':'Application submitted'}

@endpoint()
def my_applications(ctx):
    items=dbm.rows(ctx.db,'SELECT a.*,j.title,j.company,j.location FROM rozgar_applications a JOIN rozgar_jobs j ON j.id=a.job_id WHERE a.worker_id=? ORDER BY a.created_at DESC',(ctx.user['id'],))
    return {'items':items}

@endpoint()
def employer_jobs(ctx):
    items=dbm.rows(ctx.db,'SELECT j.*, (SELECT COUNT(*) FROM rozgar_applications a WHERE a.job_id=j.id) applicant_count FROM rozgar_jobs j WHERE j.employer_id=? ORDER BY j.created_at DESC',(ctx.user['id'],))
    for j in items: j['skills']=dbm.loads(j['skills'],[]); j['scam_flags']=dbm.loads(j['scam_flags'],[])
    return {'items':items}

@endpoint()
def applicants(ctx):
    jid=int(ctx.request.path_params['id'])
    job=dbm.row(ctx.db,'SELECT id FROM rozgar_jobs WHERE id=? AND employer_id=?',(jid,ctx.user['id']))
    if not job: raise ApiError(404,'Job not found')
    items=dbm.rows(ctx.db,'SELECT a.*,u.name,u.email,p.headline,p.skills,p.education,p.location,p.experience_years FROM rozgar_applications a JOIN users u ON u.id=a.worker_id LEFT JOIN rozgar_profiles p ON p.user_id=u.id WHERE a.job_id=? ORDER BY a.match_score DESC,a.created_at',(jid,))
    for a in items: a['skills']=dbm.loads(a.get('skills'),[])
    return {'items':items}

@endpoint(body=StatusIn)
def update_application(ctx,p):
    aid=int(ctx.request.path_params['id'])
    row=dbm.row(ctx.db,'SELECT a.id,j.employer_id FROM rozgar_applications a JOIN rozgar_jobs j ON j.id=a.job_id WHERE a.id=?',(aid,))
    if not row or row['employer_id']!=ctx.user['id']: raise ApiError(404,'Application not found')
    ctx.db.execute('UPDATE rozgar_applications SET status=? WHERE id=?',(p.status,aid))
    return {'message':'Applicant status updated'}

@endpoint('admin')
def moderation_queue(ctx):
    items=dbm.rows(ctx.db,"SELECT j.*,u.name employer_name,u.email employer_email FROM rozgar_jobs j JOIN users u ON u.id=j.employer_id WHERE j.status='pending' ORDER BY j.created_at",())
    for j in items: j['skills']=dbm.loads(j['skills'],[]); j['scam_flags']=dbm.loads(j['scam_flags'],[])
    return {'items':items}

@endpoint('admin',body=ModerateIn)
def moderate(ctx,p):
    jid=int(ctx.request.path_params['id'])
    cur=ctx.db.execute("UPDATE rozgar_jobs SET status=? WHERE id=? AND status='pending'",(p.status,jid))
    if not cur.rowcount: raise ApiError(404,'Pending job not found')
    dbm.audit(ctx.db,ctx.user['id'],'moderate', 'rozgar_job',jid,p.status)
    return {'message':'Job moderation saved'}

# AI-assisted Rozgar writing tools. Each uses a deterministic fallback if the AI
# provider is not configured or fails; output is advisory and must be reviewed.
class ProfileDraftIn(BaseModel):
    skills: list[str] = Field(default_factory=list, max_length=30)
    education: str = Field(default='', max_length=160)
    experience: str = Field(default='', max_length=1000)
    target_role: str = Field(default='', max_length=120)

class JobDraftIn(BaseModel):
    notes: str = Field(min_length=10, max_length=2000)

class CoverDraftIn(BaseModel):
    job_title: str = Field(min_length=2, max_length=120)
    company: str = Field(default='', max_length=120)
    skills: list[str] = Field(default_factory=list, max_length=30)
    experience: str = Field(default='', max_length=800)

@endpoint(body=ProfileDraftIn)
def profile_draft(ctx,p):
    from ..ai import extract_json
    prompt=f"Create a truthful concise job-seeker headline and 2-sentence bio. Do not invent experience. Skills: {p.skills}; education: {p.education}; experience: {p.experience}; target role: {p.target_role}. Return JSON with headline and bio."
    raw=ctx.request.app.state.ai.complete('You are a careful Indian entry-level career-writing assistant. Never invent qualifications, employers or years.',[{'role':'user','content':prompt}],400)
    data=extract_json(raw)
    if data and data.get('headline') and data.get('bio'):
        return {'headline':str(data['headline'])[:120],'bio':str(data['bio'])[:1200],'source':'claude'}
    role=p.target_role or 'entry-level professional'
    headline=f"{role} | {', '.join(p.skills[:4])}" if p.skills else role
    bio=f"{p.education + '. ' if p.education else ''}I am seeking an opportunity as a {role.lower()}. My skills include {', '.join(p.skills) if p.skills else 'a willingness to learn'}{'. ' + p.experience if p.experience else ''}."
    return {'headline':headline[:120],'bio':bio[:1200],'source':'rules'}

@endpoint(body=JobDraftIn)
def job_draft(ctx,p):
    from ..ai import extract_json
    raw=ctx.request.app.state.ai.complete('Turn employer notes into a clear, honest job listing. Never add fees, guaranteed salary or unsupported claims. Return JSON title, description, skills.',[{'role':'user','content':p.notes}],600)
    data=extract_json(raw)
    if data and data.get('title') and data.get('description'):
        return {'title':str(data['title'])[:120],'description':str(data['description'])[:5000],'skills':[str(x)[:50] for x in data.get('skills',[])[:20]],'source':'claude'}
    words=re.findall(r'[A-Za-z][A-Za-z+#.]{1,}',p.notes)
    skills=list(dict.fromkeys(w for w in words if w.lower() in {'python','sql','excel','communication','typing','sales','accounting','driving','java','react','powerbi'}))
    title=' '.join(p.notes.split()[:7]).strip().rstrip('.')[:120]
    return {'title':title or 'Job opportunity','description':p.notes.strip(),'skills':skills,'source':'rules'}

@endpoint(body=CoverDraftIn)
def cover_draft(ctx,p):
    from ..ai import extract_json
    raw=ctx.request.app.state.ai.complete('Write a brief truthful application cover note in first person. Do not invent work experience. Return JSON with cover_note.',[{'role':'user','content':f"Role: {p.job_title}; Company: {p.company}; Candidate skills: {p.skills}; Experience: {p.experience}"}],300)
    data=extract_json(raw)
    if data and data.get('cover_note'): return {'cover_note':str(data['cover_note'])[:1500],'source':'claude'}
    return {'cover_note':f"Hello, I am interested in the {p.job_title} role at {p.company or 'your organisation'}. My relevant skills include {', '.join(p.skills) if p.skills else 'a willingness to learn'}. {p.experience.strip()} I would appreciate the opportunity to discuss how I can contribute.",'source':'rules'}

@endpoint()
def applicant_summary(ctx):
    jid=int(ctx.request.path_params['id'])
    job=dbm.row(ctx.db,'SELECT title FROM rozgar_jobs WHERE id=? AND employer_id=?',(jid,ctx.user['id']))
    if not job: raise ApiError(404,'Job not found')
    apps=dbm.rows(ctx.db,'SELECT a.match_score,a.status,u.name,p.skills,p.experience_years FROM rozgar_applications a JOIN users u ON u.id=a.worker_id LEFT JOIN rozgar_profiles p ON p.user_id=u.id WHERE a.job_id=? ORDER BY a.match_score DESC',(jid,))
    skills=[]
    for a in apps:
        a['skills']=dbm.loads(a.get('skills'),[]); skills.extend(a['skills'])
    summary=f"{len(apps)} applicant(s) for {job['title']}. {(n:=sum(1 for a in apps if a['match_score']>=70))} {'has' if n==1 else 'have'} a 70% or higher skill overlap. Review each profile and interview candidates before making a decision."
    return {'summary':summary,'applicants':apps,'source':'rules'}

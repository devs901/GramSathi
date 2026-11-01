

def test_profile_create_and_update(client, citizen):
    r=client.put('/api/rozgar/profile',headers=citizen,json={'profile_type':'worker','headline':'Python fresher','skills':['Python','SQL'],'experience_years':0,'location':'Pune'})
    assert r.status_code==200, r.text
    p=client.get('/api/rozgar/profile',headers=citizen).json()['profile']
    assert p['skills']==['Python','SQL']


def test_jobs_list_and_apply(client, citizen, other):
    jobs=client.get('/api/rozgar/jobs',headers=citizen).json()['items']
    assert len(jobs)>=2
    job=next(j for j in jobs if j['title']=='Python Developer Intern')
    assert job['match_score']>=0
    applied=client.post(f"/api/rozgar/jobs/{job['id']}/apply",headers=citizen,json={'cover_note':'I know Python and SQL.'})
    assert applied.status_code==200, applied.text
    duplicate=client.post(f"/api/rozgar/jobs/{job['id']}/apply",headers=citizen,json={})
    assert duplicate.status_code==409


def test_safe_job_published_and_flagged_job_held(client, citizen, admin):
    safe=client.post('/api/rozgar/jobs',headers=citizen,json={'title':'Office Assistant','company':'Village Services','description':'Maintain office records and support citizens with application forms.','skills':['Excel'],'location':'Nashik'})
    assert safe.status_code==200 and safe.json()['status']=='published'
    flagged=client.post('/api/rozgar/jobs',headers=citizen,json={'title':'Guaranteed income job','company':'Quick Hiring','description':'Pay registration fee and send OTP on WhatsApp only to get guaranteed income.','skills':['Typing'],'location':'Remote'})
    assert flagged.status_code==200 and flagged.json()['status']=='pending'
    assert client.get('/api/admin/rozgar/moderation',headers=admin).status_code==200


def test_only_admin_can_moderate(client, citizen, admin):
    post=client.post('/api/rozgar/jobs',headers=citizen,json={'title':'Suspicious opportunity','company':'Test Corp','description':'Pay registration fee to receive job placement and guaranteed income.','skills':['Typing'],'location':'Remote'})
    jid=post.json()['id']
    assert client.post(f'/api/admin/rozgar/jobs/{jid}/moderate',headers=citizen,json={'status':'published'}).status_code==403
    assert client.post(f'/api/admin/rozgar/jobs/{jid}/moderate',headers=admin,json={'status':'published'}).status_code==200


def test_employer_can_view_applicants_and_update_status(client, citizen, other):
    # Other user posts a job; citizen applies; employer sees ranked applicant.
    job=client.post('/api/rozgar/jobs',headers=other,json={'title':'SQL Support Associate','company':'Data Works','description':'Support SQL reports, verify data and help maintain database records for customers.','skills':['SQL','Excel'],'location':'Pune'}).json()
    client.put('/api/rozgar/profile',headers=citizen,json={'profile_type':'worker','skills':['SQL','Excel'],'location':'Pune'})
    client.post(f"/api/rozgar/jobs/{job['id']}/apply",headers=citizen,json={'cover_note':'I have SQL and Excel knowledge.'})
    applicants=client.get(f"/api/rozgar/jobs/{job['id']}/applicants",headers=other)
    assert applicants.status_code==200 and applicants.json()['items'][0]['match_score']>=100
    aid=applicants.json()['items'][0]['id']
    updated=client.patch(f'/api/rozgar/applications/{aid}',headers=other,json={'status':'shortlisted'})
    assert updated.status_code==200


def test_ai_drafts_have_rules_fallback(client, citizen):
    profile=client.post('/api/ai/rozgar/profile-draft',headers=citizen,json={'skills':['Python','SQL'],'education':'B.E. AI & DS','experience':'Fresher','target_role':'Python Developer'})
    assert profile.status_code==200 and profile.json()['source']=='rules'
    assert 'Python' in profile.json()['headline']
    job=client.post('/api/ai/rozgar/job-draft',headers=citizen,json={'notes':'Python developer role. Need Python, SQL and Excel skills. Work in Nashik.'})
    assert job.status_code==200 and job.json()['source']=='rules'
    cover=client.post('/api/ai/rozgar/cover-draft',headers=citizen,json={'job_title':'Python Developer','company':'RuralTech','skills':['Python','SQL'],'experience':'Fresher'})
    assert cover.status_code==200 and 'Python Developer' in cover.json()['cover_note']


def test_employer_applicant_summary_is_owner_scoped(client, citizen, other):
    job=client.post('/api/rozgar/jobs',headers=other,json={'title':'Data Assistant','company':'Data Works','description':'Support data entry, Excel reports and database updates for customers.','skills':['Excel','SQL'],'location':'Nashik'}).json()
    assert client.get(f"/api/rozgar/jobs/{job['id']}/applicant-summary",headers=other).status_code==200
    assert client.get(f"/api/rozgar/jobs/{job['id']}/applicant-summary",headers=citizen).status_code==404


def test_duplicate_application_has_friendly_message(client, citizen):
    jid=next(j['id'] for j in client.get('/api/rozgar/jobs',headers=citizen).json()['items'] if j['title']=='Python Developer Intern')
    assert client.post(f'/api/rozgar/jobs/{jid}/apply',headers=citizen,json={}).status_code==200
    dup=client.post(f'/api/rozgar/jobs/{jid}/apply',headers=citizen,json={})
    assert dup.status_code==409 and 'already applied' in dup.json()['error'].lower()
    assert 'rozgar_applications' not in dup.text


def test_scam_check_resists_spacing_and_punctuation_tricks(client, citizen):
    for desc in ['Pay the Registration   Fee first. Easy work at home for everyone.','Send-OTP to confirm; this is a genuine long description.','GUARANTEED-INCOME every single day, no experience needed.']:
        r=client.post('/api/rozgar/jobs',headers=citizen,json={'title':'Home Work','company':'Quick Co','description':desc,'skills':[],'location':'Nashik'})
        assert r.status_code==200 and r.json()['status']=='pending', desc


def test_applicant_summary_grammar_singular(client, citizen, other, admin):
    jobs=client.get('/api/rozgar/jobs',headers=other).json()['items']
    mine=client.post('/api/rozgar/jobs',headers=citizen,json={'title':'SQL Analyst','company':'Acme','description':'Write SQL reports for the village office team.','skills':['SQL'],'location':'Nashik'}).json()['id']
    client.put('/api/rozgar/profile',headers=other,json={'profile_type':'worker','skills':['SQL'],'location':'Nashik'})
    assert client.post(f'/api/rozgar/jobs/{mine}/apply',headers=other,json={}).status_code==200
    s=client.get(f'/api/rozgar/jobs/{mine}/applicant-summary',headers=citizen).json()['summary']
    assert '1 has a 70%' in s

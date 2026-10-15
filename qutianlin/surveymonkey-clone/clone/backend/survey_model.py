"""SurveyMonkey-specific schema, opened only through the shared runtime hook."""
import json,time,uuid

def migrate(connection):
    schema='''
    CREATE TABLE IF NOT EXISTS sm_oauth_states(state TEXT PRIMARY KEY,owner TEXT NOT NULL,provider TEXT NOT NULL,expires INTEGER NOT NULL,consumed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS sm_checkouts(id TEXT PRIMARY KEY,owner TEXT NOT NULL,plan TEXT NOT NULL,users INTEGER NOT NULL,amount INTEGER NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_profiles(owner TEXT PRIMARY KEY,preferences TEXT NOT NULL DEFAULT '{}',plan TEXT NOT NULL DEFAULT 'Basic');
    CREATE TABLE IF NOT EXISTS sm_folders(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_surveys(id TEXT PRIMARY KEY,owner TEXT NOT NULL,folder_id TEXT REFERENCES sm_folders(id) ON DELETE SET NULL,title TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',theme TEXT NOT NULL DEFAULT '{}',settings TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'draft',created INTEGER NOT NULL,updated INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS sm_surveys_owner ON sm_surveys(owner,deleted,updated);
    CREATE TABLE IF NOT EXISTS sm_pages(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id) ON DELETE CASCADE,title TEXT NOT NULL DEFAULT '',description TEXT NOT NULL DEFAULT '',position INTEGER NOT NULL,logic TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS sm_questions(id TEXT PRIMARY KEY,page_id TEXT NOT NULL REFERENCES sm_pages(id) ON DELETE CASCADE,kind TEXT NOT NULL,title TEXT NOT NULL,choices TEXT NOT NULL DEFAULT '[]',required INTEGER NOT NULL DEFAULT 0,options TEXT NOT NULL DEFAULT '{}',position INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_collectors(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id) ON DELETE CASCADE,name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'weblink',token TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'open',options TEXT NOT NULL DEFAULT '{}',created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_responses(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id) ON DELETE CASCADE,collector_id TEXT NOT NULL REFERENCES sm_collectors(id),submission_key TEXT NOT NULL,answers TEXT NOT NULL,status TEXT NOT NULL,started INTEGER NOT NULL,completed INTEGER,UNIQUE(collector_id,submission_key));
    CREATE INDEX IF NOT EXISTS sm_responses_survey ON sm_responses(survey_id,status,completed);
    CREATE TABLE IF NOT EXISTS sm_notes(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id) ON DELETE CASCADE,owner TEXT NOT NULL,body TEXT NOT NULL,created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_saved_views(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id) ON DELETE CASCADE,name TEXT NOT NULL,filters TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE IF NOT EXISTS sm_attachments(id TEXT PRIMARY KEY,survey_id TEXT NOT NULL REFERENCES sm_surveys(id),collector_id TEXT REFERENCES sm_collectors(id),owner TEXT,name TEXT NOT NULL,mime TEXT NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL,created INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS sm_uploads(id TEXT PRIMARY KEY,owner TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,path TEXT NOT NULL,size INTEGER NOT NULL,created INTEGER NOT NULL);
    '''
    for statement in schema.split(';'):
        if statement.strip():connection.execute(statement)

def new_id():return uuid.uuid4().hex[:20]

def seed_demo(connection,owner):
    if connection.execute('SELECT 1 FROM sm_profiles WHERE owner=?',(owner,)).fetchone():return
    now=int(time.time());survey=new_id();page=new_id();question=new_id()
    connection.execute('INSERT INTO sm_profiles(owner) VALUES (?)',(owner,))
    connection.execute('INSERT INTO sm_surveys(id,owner,title,created,updated) VALUES (?,?,?,?,?)',(survey,owner,'Clone verification draft',now,now))
    connection.execute('INSERT INTO sm_pages(id,survey_id,position) VALUES (?,?,0)',(page,survey))
    connection.execute('INSERT INTO sm_questions(id,page_id,kind,title,choices,position) VALUES (?,?,?,?,?,0)',(question,page,'multiple_choice','How satisfied are you with this test survey?',json.dumps([{'id':new_id(),'label':label} for label in ['Very satisfied','Satisfied','Neutral','Dissatisfied','Very dissatisfied']])))

def migrate_v2(connection):
    """Add attachments, isolated provider state and checkout records to existing sites."""
    migrate(connection)

def migrate_v3(connection):
    migrate_v2(connection)
    connection.execute('CREATE TABLE IF NOT EXISTS sm_public_submissions(id TEXT PRIMARY KEY,owner TEXT NOT NULL,submission_key TEXT NOT NULL,purpose TEXT NOT NULL,fields TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(owner,submission_key))')

def seed_feedback(connection):
    """The public feedback form uses only the questions actually observed in source."""
    if connection.execute('SELECT 1 FROM sm_surveys WHERE id="site-feedback"').fetchone():return
    now=int(time.time());options=[{'id':str(i),'label':label} for i,label in enumerate(['Strongly agree','Agree','Neither agree nor disagree','Disagree','Strongly disagree'])]
    description='We’d love to hear your feedback! This survey helps us improve SurveyMonkey. To contact support, please use our help center. We also ask that you refrain from inputting personal information in the open-ended comment box.'
    connection.execute('INSERT INTO sm_surveys(id,owner,title,description,settings,status,created,updated) VALUES (?,?,?,?,?,?,?,?)',('site-feedback','surveymonkey-system','SurveyMonkey Feedback',description,json.dumps({'thank_you':'Thank you. Your feedback has been saved in this local copy.'}),'open',now,now))
    connection.execute('INSERT INTO sm_pages(id,survey_id,title,position) VALUES (?,?,?,0)',('site-feedback-page','site-feedback','Please rate the following statements:'))
    for i,title in enumerate(['SurveyMonkey’s capabilities meet my requirements.','SurveyMonkey is easy to use.','Share any additional feedback or comments below.']):
        connection.execute('INSERT INTO sm_questions VALUES (?,?,?,?,?,?,?,?)',('site-feedback-q'+str(i),'site-feedback-page','multiple_choice' if i<2 else 'comment',title,json.dumps(options if i<2 else []),i<2,'{}',i))
    connection.execute('INSERT INTO sm_collectors VALUES (?,?,?,?,?,?,?,?)',('site-feedback-collector','site-feedback','Product feedback','weblink','XRPXVQ2','open','{}',now))

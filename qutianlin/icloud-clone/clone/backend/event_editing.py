"""Transactional single-occurrence overrides and future-series splits."""
import secrets,time
from datetime import date
from backend import reminders,event_recurrence,event_invitations,calendar_archives
from backend.reminder_sharing import read


def children(db,owner,parent):
    return [e for e in reminders.rows(db,owner,'events').values() if e.get('_recurrence_parent')==parent['id']]


def selection(db,owner,event,day):
    if event_recurrence.starts_on(event,day):return event
    if event_recurrence.starts_on(event,day,include_excluded=True) and any(e['_recurrence_date']==day for e in children(db,owner,event)):
        return {**event,'_excluded':[d for d in event.get('_excluded',[]) if d!=day]}
    raise ValueError('Choose an existing occurrence of this event.')


def parent_key(db,actor,owner,parent):
    from backend import calendar_sharing
    if actor['account_id']==owner:return parent['id']
    share=calendar_sharing.owned(db,owner,parent['calendar'])
    if not share:return None
    person=calendar_sharing.member(db,share,actor)
    if person and person['status']=='accepted' and person['permission']=='write':return calendar_sharing.PREFIX+share['id']+':'+parent['id']
    return None


def annotate(db,actor,owner,event):
    parent=read(db,owner,'events',event.get('_recurrence_parent',''))
    if parent and parent.get('repeat','Never')!='Never':
        from backend import calendar_sharing
        key=parent_key(db,actor,owner,parent)
        event['_series_repeat']=parent['repeat']
        if key:event.update(_parent_key=key,_parent_revision=calendar_sharing.revision(parent))
    return event


def discard(db,actor,owner,event,now,jobs):
    jobs.extend(event_invitations.sync(db,owner,None,event,now))
    jobs.extend(event_invitations.shared_update(db,actor,owner,event,deleted=True))
    reminders.delete(db,owner,'events',event['id'],now)


def discard_children(db,actor,owner,parent,day,scope,now,jobs):
    for child in children(db,owner,parent):
        if child['_recurrence_date']==day or scope=='future' and child['_recurrence_date']>day:
            discard(db,actor,owner,child,now,jobs)


def apply(db,actor,owner,old,clean,data,dest_owner,dest_share,dest_person,now,jobs,response_source=None):
    from backend import calendar_sharing
    scope=data.get('scope');day=data.get('occurrence')
    if scope not in ('one','future'):raise ValueError('Choose only this event or this and future events.')
    selected=selection(db,owner,old,day)
    if scope=='one' and clean['repeat'] not in (old['repeat'],'Never'):raise ValueError('Apply a changed repeat interval to future events.')
    changed=event_recurrence.cancel(selected,day,scope)
    override_dates={child['_recurrence_date'] for child in children(db,owner,old)}
    response_rows=[dict(row) for row in event_invitations.rows(db,owner,response_source or old['id'])]
    for account in {owner,dest_owner}:calendar_archives.snapshot(db,account,time.time_ns()//1000000)
    # This action explicitly replaces the selected range, including prior edits
    # in that range; deleted occurrences are retained separately below.
    discard_children(db,actor,owner,old,day,scope,now,jobs)
    if changed is not None:
        reminders.save(db,owner,'events',changed,now)
        jobs.extend(event_invitations.sync(db,owner,changed,old,now))
    for field in ('_excluded','_until','_recurrence_parent','_recurrence_date'):clean.pop(field,None)
    same_identity=scope=='future' and day==old['start'][:10] and owner==dest_owner
    clean['id']=old['id'] if same_identity else secrets.token_hex(16)
    if scope=='one':
        linked=clean['repeat']!='Never';clean['repeat']='Never'
        if linked and owner==dest_owner and clean['calendar']==old['calendar']:clean.update(_recurrence_parent=old['id'],_recurrence_date=day)
    else:
        shift=date.fromisoformat(clean['start'][:10])-date.fromisoformat(day)
        if clean['repeat']!='Never':
            excluded=[d for d in old.get('_excluded',[]) if d>=day and d not in override_dates]
            clean['_excluded']=[(date.fromisoformat(d)+shift).isoformat() for d in excluded]
            if old.get('_until'):clean['_until']=(date.fromisoformat(old['_until'])+shift).isoformat()
    if owner==dest_owner and (not same_identity or response_source):
        for row in response_rows:
            if row['email'] in clean['invitees']:
                present=next((r for r in event_invitations.rows(db,owner,clean['id']) if r['email']==row['email']),None)
                if present:db.execute('UPDATE icloud_event_invites SET account_id=?,status=?,updated=?,destination=? WHERE token=?',(row['account_id'],row['status'],now,row['destination'],present['token']))
                else:db.execute('INSERT INTO icloud_event_invites (token,owner,event_id,email,account_id,status,active,updated,destination) VALUES (?,?,?,?,?,?,1,?,?)',(secrets.token_hex(20),owner,clean['id'],row['email'],row['account_id'],row['status'],now,row['destination']))
    if changed is None and not same_identity:discard(db,actor,owner,old,now,jobs)
    reminders.save(db,dest_owner,'events',clean,now)
    jobs.extend(event_invitations.sync(db,dest_owner,clean,old if owner==dest_owner else None,now))
    jobs.extend(event_invitations.shared_update(db,actor,dest_owner,clean))
    return annotate(db,actor,dest_owner,calendar_sharing.decorate(clean,dest_share,dest_person))

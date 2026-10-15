"""Connection prerequisites observed in the unauthenticated provider forms.

No cloud authentication is simulated. Provider execution remains unavailable
until a real isolated adapter is configured and independently verified.
"""
from fastapi import HTTPException
PROVIDERS={'hubspot':'HubSpot','slack':'Slack','teams':'Microsoft Teams'}
EFFECTS={'Send Slack message to channel':'slack','Notify team in Channel':'teams','Notify in Teams Chat':'teams'}
TRIGGERS={'Deal stage changes':'hubspot'}
COMPATIBLE={'Deal stage changes':['Create project']}

def status(provider):
 if provider not in PROVIDERS:raise HTTPException(404,'Connection not found.')
 return {'provider':provider,'name':PROVIDERS[provider],'connected':False,'channels':[],'status':'not_configured','message':PROVIDERS[provider]+' connection is not configured for this workspace.'}

def require(rule):
 provider=TRIGGERS.get(rule['trigger'])
 if not provider:provider=next((EFFECTS[a['effect']] for a in rule['actions'] if a['effect'] in EFFECTS),None)
 if provider:raise HTTPException(412,PROVIDERS[provider]+' authentication is required before saving this automation.')

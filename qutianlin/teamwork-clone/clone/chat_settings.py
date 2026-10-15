"""Source-backed Chat settings, persisted for the current actor and workspace."""
import json
from pathlib import Path
from fastapi import HTTPException, Request

TIMEZONES = json.loads((Path(__file__).parent / 'static/chat-timezones.json').read_text())
ZONES = {row['id']: row['referenceCode'] for row in TIMEZONES}
DEFAULTS = {'timezoneId': 115, 'timeFormat': '12hr', 'defaultNotificationNoisiness': 'mentions', 'emailNotifications': 'always', 'sendNotificationsWhenOnline': 'never', 'notificationSound': 'pop', 'embeddedChat': 'enabled'}
PREVIEWS = ['teamworkCardsPreview', 'attachedImagePreview', 'attachedFilePreview', 'urlPreview', 'showMovieQuotes']
DEFAULTS.update({key: 'always' for key in PREVIEWS})
CHOICES = {'timeFormat': ['12hr', '24hr'], 'defaultNotificationNoisiness': ['all', 'mentions', 'directMentions', 'none'], 'emailNotifications': ['always', 'never'], 'sendNotificationsWhenOnline': ['always', 'never'], 'notificationSound': ['classic', 'alert', 'bottle', 'bubble', 'buckle', 'click', 'mallet', 'pop', 'wood']}

CHOICES['embeddedChat']=['enabled','disabled']
CHOICES.update({key: ['always', 'never'] for key in PREVIEWS})


def settings(c, who, actor):
    row = c.execute('SELECT value FROM tw_preferences WHERE owner=? AND key=?',
                    (actor, 'chat_settings:' + who)).fetchone()
    return {**DEFAULTS, **(json.loads(row['value']) if row else {})}


def timezone(c, who, actor):
    return ZONES[settings(c, who, actor)['timezoneId']]


def install(app, db, identity):
    @app.get('/api/chat/settings')
    def get(req: Request):
        with db() as c:
            who, actor = identity(req, c)
            return settings(c, who, actor)

    @app.patch('/api/chat/settings')
    async def save(req: Request):
        try:
            data = await req.json()
        except ValueError:
            raise HTTPException(422, 'Choose a valid Chat setting.')
        with db() as c:
            who, actor = identity(req, c)
            if not isinstance(data, dict) or not data or set(data) - DEFAULTS.keys():
                raise HTTPException(422, 'Choose a valid Chat setting.')
            if 'timezoneId' in data and (type(data['timezoneId']) is not int or data['timezoneId'] not in ZONES):
                raise HTTPException(422, 'Choose a timezone from the list.')
            for key, choices in CHOICES.items():
                if key in data and (not isinstance(data[key], str) or data[key] not in choices):
                    raise HTTPException(422, 'Choose a valid ' + key + ' setting.')
            value = {**settings(c, who, actor), **data}
            c.execute('INSERT INTO tw_preferences VALUES(?,?,?) ON CONFLICT(owner,key) DO UPDATE SET value=excluded.value',
                      (actor, 'chat_settings:' + who, json.dumps(value)))
            return value

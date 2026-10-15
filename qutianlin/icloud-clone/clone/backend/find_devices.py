"""Local device-command adapter. No network or physical-device integration."""
import json
import time


def migrate(db):
    db.execute('CREATE TABLE IF NOT EXISTS icloud_device_actions (owner TEXT NOT NULL, device TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner,device))')


def states(db, owner):
    return {row['device']: json.loads(row['payload']) for row in db.execute(
        'SELECT device,payload FROM icloud_device_actions WHERE owner=?', (owner,))}


def act(db, owner, identifier, data):
    if not isinstance(data, dict):
        raise ValueError('Choose a device action.')
    action = data.get('action')
    capabilities = {'play_sound':'play_sound', 'stop_sound':'play_sound',
                    'lost_mode':'lost_mode', 'stop_lost_mode':'lost_mode',
                    'erase':'erase', 'cancel_erase':'erase', 'remove':'remove'}
    if action not in capabilities:
        raise ValueError('Choose a device action.')
    row = db.execute("SELECT payload FROM icloud_entities WHERE owner=? AND kind='devices' AND id=?", (owner, identifier)).fetchone()
    if not row:
        raise LookupError('Device not found.')
    device = json.loads(row[0])
    if not device.get('capabilities', {}).get(capabilities[action]):
        raise PermissionError('This device does not support that action.')
    state = states(db, owner).get(identifier, {})
    if state.get('removed'):
        raise LookupError('This device has been removed from the local list.')
    if action in ('erase', 'remove') and data.get('confirmed') is not True:
        raise ValueError('Confirm this action to continue.')
    online = str(device.get('status')) == '200'
    if action == 'play_sound':
        state['sound'] = 'playing' if online else 'pending'
    elif action == 'stop_sound':
        state.pop('sound', None)
    elif action == 'lost_mode':
        phone, message = data.get('phone', ''), data.get('message', '')
        if not isinstance(phone, str) or len(phone) > 80 or not isinstance(message, str) or len(message) > 250:
            raise ValueError('Enter a phone number and a message of up to 250 characters.')
        state['lost_mode'] = {'status':'active' if online else 'pending', 'phone':phone.strip(), 'message':message.strip()}
    elif action == 'stop_lost_mode':
        state.pop('lost_mode', None)
    elif action == 'erase':
        state['erase'] = 'completed' if online else 'pending'
    elif action == 'cancel_erase':
        if state.get('erase') != 'pending':
            raise ValueError('There is no pending erase to cancel.')
        state.pop('erase', None)
    elif action == 'remove':
        state = {'removed':True}
    state.update(updated_at=int(time.time()), simulated=True)
    db.execute('INSERT INTO icloud_device_actions VALUES (?,?,?) ON CONFLICT(owner,device) DO UPDATE SET payload=excluded.payload',
               (owner, identifier, json.dumps(state)))
    return state

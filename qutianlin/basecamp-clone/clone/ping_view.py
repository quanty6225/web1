"""Ping layout using the captured native chat composer and evidenced sidebar."""
from functools import lru_cache
from pathlib import Path
from lxml import html, etree

ROOT=Path(__file__).parent


@lru_cache(maxsize=1)
def template():
    source=ROOT/'frontend/pages/6302022/buckets/49234166/chats/10398823039/index.html'
    tree=html.fromstring(source.read_text())
    return html.tostring(tree.xpath('//bc-chat-room')[0],encoding='unicode')


def conversation(identifier,title,members,account_id,cover=None):
    markup=template().replace('/6302022/buckets/49234166/chats/10398823039','/6302022/circles/'+identifier).replace('10398823039',identifier)
    room=html.fromstring(markup);room.set('data-local-ping',identifier);room.set('data-room-kind','circle');room.set('data-local-chat-base','/api/pings/'+identifier)
    room.set('data-campfire-person','{}')
    for node in room.xpath('.//footer'):node.set('id','chat_footer_ping_'+identifier)
    for node in room.xpath('.//*[@data-autosave-key]'):node.set('data-autosave-key','local-ping:'+account_id+':'+identifier)
    for node in room.xpath('.//lexxy-editor'):
        node.set('data-direct-upload-url','/api/pings/'+identifier+'/files/direct')
        node.set('data-blob-url-template','/api/pings/'+identifier+'/files/:signed_id/:filename')
    # Rich text loads asynchronously. Do not expose an active microphone
    # before its native recording listener has been installed.
    for node in room.xpath('.//button[@name="voice-note"]'):
        node.set('disabled','');node.set('data-local-voice-pending','')
    # The local API loads the complete durable transcript. The native paginator
    # must not request the conversation shell as another history page.
    for node in room.xpath('.//bc-infinite-page'):node.set('reached-infinity','')
    for node in room.xpath('.//*[@data-behavior="chat_lines"]'):
        for child in list(node):node.remove(child)
        node.text=''
    for node in room.xpath('.//*[contains(@class,"blank-slate--chat")]|.//turbo-cable-stream-source'):
        node.getparent().remove(node)
    for node in room.xpath('.//header[contains(@class,"chat__header")]'):
        for child in list(node):node.remove(child)
        node.attrib.pop('hidden',None)
        node.set('class','chat__header')
        image=etree.SubElement(node,'img',{'class':'avatar','width':'56','height':'56','alt':'Ping cover','data-local-ping-cover':''})
        if cover:image.set('src',cover)
        else:image.set('hidden','');image.set('class','avatar hidden')
        header_body=etree.SubElement(node,'div',{'class':'inline-edit-form'})
        header_body=etree.SubElement(header_body,'div',{'class':'chat__header-body'})
        heading=etree.SubElement(header_body,'h1',{'class':'margin-block-0'})
        etree.SubElement(heading,'a',{'href':'/6302022/my/sidebar/circles/'+identifier+'/edit','data-turbo-frame':'sidebar_frame','data-local-ping-title':''}).text=title
        etree.SubElement(header_body,'p',{'class':'chat__header-people margin-block-0','data-local-ping-participants':''}).text='Ping with '+', '.join(person['name'] for person in members)
        menu=etree.SubElement(node,'details',{'class':'chat__header-options'})
        etree.SubElement(menu,'summary',{'class':'btn btn--icon btn--sm btn--ghost','aria-label':'Ping options'}).text='•••'
        etree.SubElement(menu,'a',{'href':'/6302022/my/sidebar/circles/'+identifier+'/uploads','data-turbo-frame':'sidebar_frame','class':'btn btn--sm btn--ghost'}).text='See all files posted here'
        etree.SubElement(menu,'button',{'type':'button','class':'btn btn--sm btn--ghost','data-local-ping-archive':identifier}).text='Archive this Ping…'
    for node in room.xpath('.//lexxy-prompt[@name="mention"]'):node.set('src','/6302022/prompts/people')
    wrapper=etree.Element('section',{'class':'sidebar__chat','data-controller':'sidebar--chat','data-sidebar-target':'chat','data-bridge-ping-path':'/6302022/circles/'+identifier})
    panel=etree.SubElement(wrapper,'div',{'class':'chat-panel'})
    container=etree.SubElement(panel,'div',{'class':'chat chat--scrollable text-16'})
    container.append(room)
    return wrapper


def settings(identifier,record,members,cover=None):
    section=etree.Element('section',{'class':'padding-24','data-local-ping-settings-panel':''})
    etree.SubElement(section,'a',{'href':'/6302022/my/sidebar/circles/'+identifier,'data-turbo-frame':'sidebar_frame'}).text='Back to Ping'
    form=etree.SubElement(section,'form',{'data-local-ping-settings':identifier})
    image=etree.SubElement(form,'img',{'class':'avatar','width':'80','height':'80','alt':'Ping cover','data-local-ping-cover':''})
    if cover:image.set('src',cover)
    else:image.set('hidden','');image.set('class','avatar hidden')
    label=etree.SubElement(form,'label',{'class':'block margin-block-16'});label.text='Cover image'
    etree.SubElement(label,'input',{'type':'file','accept':'image/*','data-local-ping-cover-upload':identifier})
    remove=etree.SubElement(form,'button',{'type':'button','class':'btn btn--sm btn--ghost','data-local-ping-cover-remove':identifier});remove.text='Remove cover image'
    if not cover:remove.set('hidden','');remove.set('class',remove.get('class')+' hidden')
    label=etree.SubElement(form,'label',{'class':'block margin-block-16'});label.text='Ping name'
    etree.SubElement(label,'input',{'class':'input input--full-width','name':'title','value':record['title'],'placeholder':'Give this ping a name…','maxlength':'200'})
    group=etree.SubElement(form,'div',{'data-local-ping-members':'','aria-label':'People in this Ping'})
    for member in members:
        row=etree.SubElement(group,'div',{'class':'flex align-center gap-8 margin-block-8','data-ping-member':member['account']})
        etree.SubElement(row,'img',{'class':'avatar','width':'32','height':'32','src':'/api/avatar.svg?person='+member['account'],'alt':''})
        etree.SubElement(row,'span').text=member['name']
        etree.SubElement(row,'button',{'type':'button','class':'btn btn--icon btn--sm btn--ghost','data-local-ping-remove-member':'','aria-label':'Remove '+member['name']}).text='×'
    picker=etree.SubElement(form,'bc-autocomplete',{'url':'/6302022/autocompletables/circles/people','multiple':'','class':'input input--autocomplete margin-block-16'})
    etree.SubElement(picker,'input',{'type':'text','dir':'auto','id':'ping-settings-people','name':'circle[users]','placeholder':'Add a person…','aria-label':'Add a person'})
    etree.SubElement(form,'p',{'class':'text-subtle'}).text='Note: Anyone you add will see the full chat history, including messages that were sent before they joined.'
    etree.SubElement(form,'button',{'type':'submit','class':'btn btn--primary'}).text='Save'
    return section

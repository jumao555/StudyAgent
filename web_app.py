import json
import logging
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4
import streamlit as st
from database import load_session, list_plans, update_plan_status
from main import run_agent
from plan_service import init_storage, list_sessions, prepare_plan, list_drafts, decide_draft
from tools.plan_tools import open_plan

USER_ID = 'user_A'
st.set_page_config(page_title='StudyAgent',page_icon='📚',layout='wide')
st.title('📚 StudyAgent')
st.caption('查阅自己的笔记，制定学习计划，记录完成情况。')
try:
    init_storage()
    sessions = list_sessions(USER_ID)
except sqlite3.Error:
    st.error('无法连接数据库，请检查本地文件权限。')
    st.stop()
if 'active_session' not in st.session_state:
    st.session_state.active_session = sessions[0] if sessions else 'default'
with st.sidebar:
    st.header('学习会话')
    if st.button('新建会话',use_container_width=True):
        st.session_state.active_session = 'chat_'+uuid4().hex[:12]
        st.rerun()
    options = list(dict.fromkeys([st.session_state.active_session]+sessions))
    selected = st.selectbox('选择会话',options,index=0)
    if selected != st.session_state.active_session:
        st.session_state.active_session = selected
        st.rerun()
    st.caption('本机单人使用。计划保存前需在页面确认。')
session_id = st.session_state.active_session
if 'notice' in st.session_state:
    st.success(st.session_state.pop('notice'))
chat_tab, plan_tab = st.tabs(['💬 学习助手','📋 学习计划'])
with chat_tab:
    try:
        state = load_session(USER_ID,session_id)
        drafts = list_drafts(USER_ID,session_id)
    except sqlite3.Error:
        st.error('无法读取会话，请稍后重试。')
        st.stop()
    messages = state['messages'] if state else []
    if not messages:
        st.info('试试：根据 Kotlin 笔记制定一个30分钟复习计划并保存。')
    for m in messages:
        if m['role'] in ('user','assistant') and m.get('content'):
            with st.chat_message(m['role']):
                st.markdown(m['content'])
    if state and state['status'] in ('failed','stopped','running'):
        labels = {'failed':'上次任务失败，可以重试。','stopped':'上次任务达到限制或被停止，可能尚未完成。','running':'上次任务可能被中断，请检查已有结果后再提交。'}
        st.warning(labels[state['status']])
    with st.expander('查看工具执行记录'):
        calls = {c['id']:c for m in messages for c in m.get('tool_calls',[])}
        if not calls:
            st.caption('当前会话还没有工具调用。')
        for m in messages:
            if m['role']=='tool':
                function = calls.get(m.get('tool_call_id'),{}).get('function',{})
                st.markdown('**'+function.get('name','工具')+'**')
                st.code(function.get('arguments','{}'),language='json')
                try:
                    st.json(json.loads(m['content']))
                except (ValueError,TypeError):
                    st.text(m['content'])
    for draft in drafts:
        with st.container(border=True):
            st.subheader('待确认：'+draft['title'])
            st.caption('草稿已保留，尚未保存为正式计划。')
            st.markdown(draft['content'])
            yes,no = st.columns(2)
            confirm = yes.button('确认保存',key='confirm_'+draft['id'],type='primary')
            cancel = no.button('取消',key='cancel_'+draft['id'])
            if confirm or cancel:
                try:
                    result = decide_draft(USER_ID,session_id,draft['id'],confirm)
                except (sqlite3.Error,OSError,ValueError):
                    st.error('处理失败，草稿仍保留。若文件已生成，重试会检查内容，不会覆盖其他文件。')
                else:
                    st.session_state.notice = '计划已保存，可在学习计划中查看。' if result['status']=='saved' else '已取消保存。'
                    st.rerun()
    prompt = st.chat_input('输入学习问题或计划需求',disabled=bool(drafts),key='prompt_'+session_id)
    if drafts:
        st.caption('请先处理待确认计划，再继续聊天。')
    if prompt and prompt.strip():
        try:
            with st.spinner('正在查阅资料并处理任务……'):
                run_agent(prompt.strip(),session_id,plan_handler=lambda title,content:prepare_plan(USER_ID,session_id,title,content))
        except Exception as exc:
            logging.getLogger(__name__).error('网页任务异常 type=%s',type(exc).__name__)
            st.error('任务未正常完成，请检查模型服务和本地配置后重试。已有记录仍保留。')
        else:
            st.rerun()
with plan_tab:
    try:
        plans = list_plans(USER_ID)
    except sqlite3.Error:
        st.error('无法读取计划列表。')
        st.stop()
    pending = sum(p['status']=='pending' for p in plans)
    left,right = st.columns(2)
    left.metric('待完成计划',pending)
    right.metric('已完成计划',len(plans)-pending)
    if not plans:
        st.info('还没有计划。聊天中生成计划并确认保存后，会出现在这里。')
    for plan in plans:
        completed = plan['status']=='completed'
        with st.expander(plan['title']+(' · 已完成' if completed else ' · 待完成')):
            created = datetime.fromisoformat(plan['created_at']).replace(tzinfo=timezone.utc).astimezone()
            st.caption('创建时间：'+created.strftime('%Y-%m-%d %H:%M'))
            result = open_plan(USER_ID,plan['id'])
            if result['ok']:
                st.markdown(result['content'])
                st.download_button('下载计划',result['content'],file_name=plan['filename'],mime='text/markdown',key='download_'+str(plan['id']))
            else:
                st.warning(result['error'])
            if st.button('改回待完成' if completed else '标记完成',key='status_'+str(plan['id'])):
                try:
                    changed = update_plan_status(USER_ID,plan['id'],'pending' if completed else 'completed')
                except (sqlite3.Error,ValueError):
                    st.error('状态更新失败，请重试。')
                else:
                    if changed:
                        st.rerun()
                    st.warning('该计划已不存在。')

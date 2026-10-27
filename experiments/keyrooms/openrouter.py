"""Read credentials only inside the request process; never include them in logs."""
import json,re,time,os
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

def load_key(path):
    # Deliberately never print input, matching text, key length or key fragments.
    value=os.environ.get('OPENROUTER_API_KEY')
    if value:return value
    source=Path(path).read_text()
    match=re.search(r'^\s*Openrouter\s*[:：]\s*[`\"\']?([^\s`\"\']+)',source,re.I|re.M)
    if not match:raise ValueError('OpenRouter credential entry missing or malformed')
    value=match.group(1)
    if value.lower() in ('xxxx','xxx','your_key'):raise ValueError('OpenRouter credential is a placeholder')
    return value

class APIRequestError(RuntimeError):
    def __init__(self,info):
        self.info=info
        super().__init__(info['message'])

def http_error_info(status,payload,secret):
    """Keep only bounded error messages/codes, never headers or raw request bodies."""
    def clean(value,limit=1500):
        value=str(value)
        if secret:value=value.replace(secret,'[REDACTED]')
        value=re.sub(r'(?i)Bearer\s+[^\s"\']+','Bearer [REDACTED]',value)
        value=re.sub(r'sk-[A-Za-z0-9_-]+','[REDACTED]',value)
        return value[:limit]
    error=payload.get('error',{}) if isinstance(payload,dict) else {}
    if not isinstance(error,dict):error={'message':error}
    details=[]
    if error.get('message'):details.append(clean(error['message']))
    metadata=error.get('metadata',{})
    if isinstance(metadata,dict) and isinstance(metadata.get('raw'),str):
        try:
            nested=json.loads(metadata['raw']);nested=nested.get('error',nested)
            if isinstance(nested,dict) and nested.get('message'):details.append(clean(nested['message']))
        except (ValueError,AttributeError):pass
    detail=' | '.join(details)[:2500]
    context=any(term in detail.lower() for term in ('context length','context window','maximum context','too many tokens','max model length','max_tokens +','input tokens +'))
    global_error=status in (401,402,403,404)
    return {'kind':'context_limit' if context else 'authentication' if status==401 else 'billing' if status==402 else 'access_or_endpoint' if status in (403,404) else 'http_error',
        'http_status':status,'scope':'batch' if global_error else 'episode','retryable':status in (408,429,500,502,503,504),
        'message':f'OpenRouter HTTP {status}'+(': '+detail if detail else ''),'code':clean(error.get('code',''),100)}

def remaining_output_budget(message,current,context_length):
    """Use server-reported counts including tools; lower-bound reports require backoff."""
    text=message.lower().replace(',', '')
    patterns=[r"(\d+)\s+(?:of\s+)?(?:text\s+)?input\s+tokens", r"(\d+)\s+of\s+text\s+input", r"(?:input|prompt)(?:\s+token)?(?:\s+count|\s+length|\s+tokens)?\s*(?:is|:|=|\()\s*(\d+)"]
    # OpenRouter reports text and tool tokens separately; its total includes both.
    total=re.search(r'requested\s+(?:about\s+)?(\d+)\s+tokens',text)
    if total:
        available=context_length-(int(total.group(1))-current)
        return available if 0<available<current else None
    # Together sometimes reports only a lower bound, not the actual prompt size.
    if 'at least' in text:
        available=current-4096
        return available if available>0 else None
    prompt=None
    for pattern in patterns:
        match=re.search(pattern,text)
        if match:prompt=int(match.group(1));break
    if prompt is None:
        match=re.search(r'requested\s+(?:about\s+)?(\d+)\s+tokens',text)
        if match:prompt=int(match.group(1))-current
    if prompt is None or prompt<0:return None
    available=min(current,context_length-prompt)
    return available if 0<available<current else None

class OpenRouterClient:
    def __init__(self,key_file,model='meta/muse-glimmer-30b',max_calls=800,spend_limit_usd=5):
        self._key=load_key(key_file);self.calls=0;self.max_calls=max_calls;self.cost=0.;self.last_metadata={}
        self.config={'client':'openrouter','model':model,'temperature':0,'max_tokens':117964 if model=='meta/muse-glimmer-30b' else 8192,'reasoning':{'enabled':True},'tool_choice':'required','single_action_enforcement':'host_validation','max_calls':max_calls,'spend_limit_usd':spend_limit_usd}
        self.config.update(context_length=131072 if model=='meta/muse-glimmer-30b' else None,output_budget_policy='maximum_supported_then_server_exact_remaining',request_timeout_seconds=1800)
    def complete(self,messages,tools):
        if (self.max_calls is not None and self.calls>=self.max_calls) or self.cost>=self.config['spend_limit_usd']:raise RuntimeError('Request/spend limit reached')
        body={k:self.config[k] for k in ('model','temperature','max_tokens','reasoning','tool_choice')}
        body.update(messages=messages,tools=tools,provider={'require_parameters':True})
        # Explicitly disable middleware history compression. Full history is retained.
        body['transforms']=[]
        if self.config['model']=='meta/muse-glimmer-30b':body['provider'].update(only=['together'],allow_fallbacks=False)
        self.calls+=1;started=time.time();self.last_metadata={}
        attempts=0;adjustments=[]
        while True:
            attempts+=1
            request=Request('https://openrouter.ai/api/v1/chat/completions',json.dumps(body).encode(),{'Content-Type':'application/json','Authorization':'Bearer '+self._key})
            try:
                with urlopen(request,timeout=self.config['request_timeout_seconds']) as response:data=json.load(response)
                break
            except HTTPError as exc:
                if exc.code in (429,500,502,503,504) and attempts<4:
                    time.sleep(min(2**attempts,15));continue
                try:payload=json.loads(exc.read(65536))
                except (ValueError,OSError):payload={}
                info=http_error_info(exc.code,payload,self._key)
                if info['kind']=='context_limit' and self.config['context_length'] and len(adjustments)<32:
                    available=remaining_output_budget(info['message'],body['max_tokens'],self.config['context_length'])
                    if available is not None:
                        adjustments.append({'from':body['max_tokens'],'to':available,'server_message':info['message']});body['max_tokens']=available;continue
                self.last_metadata={'error':info,'wall_seconds':time.time()-started,'transport_attempts':attempts,'requested_max_tokens':body['max_tokens'],'context_adjustments':adjustments}
                raise APIRequestError(info) from None
            except (URLError,TimeoutError):
                if attempts<4:time.sleep(min(2**attempts,15));continue
                info={'kind':'transport','scope':'episode','retryable':True,'message':'OpenRouter transport failure'}
                self.last_metadata={'error':info,'wall_seconds':time.time()-started,'transport_attempts':attempts}
                raise APIRequestError(info) from None
        if data.get('error'):
            code=data['error'].get('code',502) if isinstance(data['error'],dict) else 502
            try:code=int(code)
            except (TypeError,ValueError):code=502
            info=http_error_info(code,data,self._key);self.last_metadata={'error':info}
            raise APIRequestError(info)
        choice=data['choices'][0];usage=data.get('usage',{});self.cost+=float(usage.get('cost') or 0)
        self.last_metadata={'id':data.get('id'),'model':data.get('model'),'provider':data.get('provider'),'usage':usage,'finish_reason':choice.get('finish_reason'),'wall_seconds':time.time()-started,'transport_attempts':attempts,'requested_max_tokens':body['max_tokens'],'context_adjustments':adjustments}
        if choice.get('finish_reason')=='length':
            info={'kind':'generation_limit','scope':'episode','retryable':False,'message':'Generation limit reached; incomplete action not executed'}
            self.last_metadata['error']=info
            raise APIRequestError(info)
        return choice['message']

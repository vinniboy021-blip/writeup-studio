# Contratos API para integração

API `/api/v1`. GET listas usa `{items,total,page,page_size}`. GET resource retorna objeto.
Cookies `ctf_session`, requisições com credentials include; auth login/register retorna `{user:{id,email,name,is_admin},csrf_token}`; auth/me também `{user,csrf_token}`. Mutações autenticadas header X-CSRF-Token.
IDs UUID string. Datetimes ISO UTC.

## Rotas
- Auth: POST `/auth/register`, `/auth/login`, `/auth/logout`; GET `/auth/me`,`/auth/sessions`; DELETE `/auth/sessions/{id}`; POST `/auth/password`.
- Dashboard: GET `/dashboard` inclui competitions,challenges,writeups,evidences,completed_writeups,in_progress_writeups,recent_activity,category_stats,competition_progress.
- CRUD `/competitions`,`/challenges`: GET/POST list; GET/PATCH/DELETE `/{id}`. Challenge category string, custom categories GET/POST `/categories`.
- `/teams` GET/POST; `/teams/{id}` GET/PATCH; `/teams/{id}/members` GET; POST/PATCH member; POST `/teams/{id}/invites` {email,role}; POST `/teams/invites/accept` {token}.
- `/templates` GET/POST, `/{id}` GET/PATCH, `/{id}/revisions` GET, `/import` POST, `/{id}/export` GET. Default 10 templates.
- `/writeups` GET/POST. `/writeups/{id}` GET/PATCH/DELETE. PATCH {title?,document?,status?,expected_version}. POST accepts challenge_id?,team_id?,template_id?, document.
- `/writeups/{id}/revisions` GET; POST `/writeups/{id}/revisions/{rid}/restore` {expected_version}; GET `/writeups/{id}/diff?from_version=1&to_version=2`.
- `/evidences` GET/POST multipart file,origin,name?,description?,team_id?,challenge_id?,captured_at?,tags?; `/evidences/{id}` GET/PATCH/DELETE.
- `/evidences/{id}/download` GET; `/evidences/{id}/thumbnail` GET; `/evidences/{id}/annotations` GET/POST {expected_version,data}; `/evidences/{id}/versions` GET; `/evidences/{id}/versions/{version_id}/download` GET.
- Annotations data {schema_version:1,width,height,shapes:[{id,type,x,y,x2?,y2?,width?,height?,text?,color?,strokeWidth?,number?}],crop?:{x,y,width,height}}; arrow,rect,circle,line,text,highlight,step,blur,redact.
- `/writeups/{id}/evidences` GET/POST {evidence_id,section_id?,position?}; DELETE `/writeups/{id}/evidences/{evidence_id}`. `/timeline` GET filters evidence_id?,writeup_id?.
- `/writeups/{id}/comments` GET/POST {body,section_id?}; PATCH `/comments/{id}` {resolved:true}.
- `/writeups/{id}/reviews` GET/POST {reviewer_id,comment?}; POST `/reviews/{id}/decision` {decision:approved|changes_requested,comment?}. Author cannot approve; approved review version must match.
- `/notifications` GET; PATCH `/notifications/{id}` {read:true}; `/audit` GET.
- `/search` GET q,category,tags,author_id,tool,language,date_from,date_to,sort,page,page_size.
- POST `/writeups/{id}/exports` {format:markdown|html|pdf|json,include_evidences:false,include_originals:false,cover:true,theme:dark|light,brand?,header?,footer?}; GET `/exports/{id}`; GET `/exports/{id}/download`; POST `/exports/{id}/cancel`.
- POST `/writeups/{id}/publish` {visibility:private|team|public,expected_version,confirm_public:false}; GET `/public/writeups/{id}` snapshot aprovado com somente conteúdo compartilhável.
- `/ai/providers` GET; `/ai/jobs` GET/POST {task,notes?,writeup_id?,evidence_ids:[],provider:ollama,external_consent:false}; `/{id}` GET; `/{id}/cancel` POST; resultados provenance,facts,inferences,draft,human_review_required.
- `/kali/status` GET; `/kali/tools` GET; `/kali/run` POST {tool,arguments:{},evidence_id?,confirm:true}; saída evidence_id,stdout,stderr,exit_code,started_at,finished_at,sha256,provenance quando aplicável. Backward command compat apenas parsing restrito.
- `/admin/settings` GET/PATCH; `/admin/users` GET/PATCH.

## Modelos compartilhados
User(id,email,name,password_hash,is_admin,is_active,created_at); SessionModel(id,user_id,token_hash,csrf_token,expires_at,revoked_at,created_at).
Team(id,name,description,owner_id); TeamMember(team_id,user_id,role); TeamInvite(id,team_id,email,role,token_hash,expires_at,accepted_at,created_by).
Competition(id,owner_id,team_id,name,description,platform,url,start_at,end_at,status,mode,tags,visibility,deleted_at,created_at,updated_at,version).
Challenge(id,owner_id,team_id,competition_id,name,category,difficulty,points,status,description,references,notes,tags,visibility,deleted_at,created_at,updated_at,version).
Writeup(id,owner_id,team_id,challenge_id,title,document,status,visibility,version,approved_revision,published_at,deleted_at,created_at,updated_at).
WriteupRevision(id,writeup_id,version,title,document,author_id,message,created_at).
WriteupTemplate(id,owner_id nullable,team_id,name,description,document,version); TemplateRevision(id,template_id,version,document,author_id).
Evidence(id,owner_id,team_id,challenge_id,name,description,origin,captured_at,received_at,sha256,size,mime_type,extension,storage_key,version,tags,metadata_json,visibility,deleted_at,created_at,updated_at).
EvidenceVersion(id,evidence_id,version,storage_key,sha256,size,mime_type,author_id,kind,created_at); EvidenceAnnotation(id,evidence_id,author_id,version,data,created_at); EvidenceEvent(id,evidence_id,actor_id,event_type,details,created_at).
WriteupEvidence(id,writeup_id,evidence_id,section_id,position). Comment(id,writeup_id,author_id,body,section_id,resolved_at,created_at).
ReviewRequest(id,writeup_id,requester_id,reviewer_id,status,version,comment,decided_at,created_at).
Notification(id,user_id,kind,title,body,entity_id,read_at,created_at); Export(id,writeup_id,requested_by,format,status,options,storage_key,error,version,created_at,updated_at).
AIJob(id,owner_id,team_id,writeup_id,task,provider,status,input_data,output_data,error,config_snapshot,external_consent,cancel_requested,created_at,updated_at).
Publication(id,writeup_id,owner_id,team_id,version,title,document,visibility,expires_at,created_at).
AuditLog(id,actor_id,action,entity_type,entity_id,details,correlation_id,created_at); ApplicationSetting(key,value,updated_by,updated_at).
Demais entidades do prompt: Role,Permission,RolePermission,CompetitionMember,ChallengeAssignment,Category,Tag.

Módulos: identity,workspace,studio,evidence,integrations. Nomes modelos antigos aliases Revision=WriteupRevision,Template=WriteupTemplate,Review=ReviewRequest,Annotation=EvidenceAnnotation.

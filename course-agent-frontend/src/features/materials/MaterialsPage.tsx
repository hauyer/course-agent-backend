import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { CircleHelp, FileText, Library, RefreshCw, Trash2, Upload, X } from "lucide-react";
import { api, type Entity } from "../../api";
import "./materials.css";

type UploadJob = {
  id: string;
  name: string;
  percent: number;
  status: "uploading" | "processing" | "done" | "error";
  error?: string;
};

let uploadJobs: UploadJob[] = [];
const uploadListeners = new Set<(jobs: UploadJob[]) => void>();
function publishUploads() {
  const snapshot = [...uploadJobs];
  uploadListeners.forEach((listener) => listener(snapshot));
}
function updateUpload(id: string, patch: Partial<UploadJob>) {
  uploadJobs = uploadJobs.map((job) => job.id === id ? { ...job, ...patch } : job).slice(-5);
  publishUploads();
}
function useUploadJobs() {
  const [jobs, setJobs] = useState<UploadJob[]>(uploadJobs);
  useEffect(() => {
    uploadListeners.add(setJobs);
    setJobs([...uploadJobs]);
    return () => { uploadListeners.delete(setJobs); };
  }, []);
  return jobs;
}
async function watchProcessing(jobId: string, courseId: number, materialId: number) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    try {
      const materials: any = await api.materials(courseId);
      const material = unwrap(materials).find((item) => Number(item.id) === Number(materialId));
      if (material?.parse_status === "success") {
        updateUpload(jobId, { status: "done", percent: 100 });
        return;
      }
      if (material?.parse_status === "failed") {
        updateUpload(jobId, { status: "error", error: material.parse_error || "资料解析失败" });
        return;
      }
    } catch {
      // 页面切换或短暂断网不会中止后台任务，下一轮继续确认状态。
    }
  }
  updateUpload(jobId, { status: "processing", error: "后台仍在处理，可稍后刷新资料列表查看" });
}
async function startUpload(courseId: number, form: FormData) {
  const file = form.get("file") as File;
  const id = `${Date.now()}-${Math.random()}`;
  const job: UploadJob = {
    id,
    name: file?.name || "课程资料",
    percent: 0,
    status: "uploading",
  };
  uploadJobs = [...uploadJobs, job].slice(-5);
  publishUploads();
  try {
    const result: any = await api.uploadMaterial(courseId, form, (percent) => updateUpload(id, { percent }));
    updateUpload(id, { percent: 100, status: "processing" });
    void watchProcessing(id, courseId, Number(result.id));
    return result;
  } catch (error) {
    updateUpload(id, { status: "error", error: errorText(error) });
    throw error;
  }
}

function unwrap(data:any):Entity[]{return Array.isArray(data)?data:data?.items||[]}
function errorText(error:unknown){return error instanceof Error?error.message:"操作失败"}
function dateText(value?:string){return value?new Intl.DateTimeFormat("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value)):"—"}
function useData<T>(loader:()=>Promise<T>,deps:any[]=[]){const[data,setData]=useState<T|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true),[tick,setTick]=useState(0);useEffect(()=>{let live=true;setLoading(true);loader().then(value=>live&&setData(value)).catch(reason=>live&&setError(errorText(reason))).finally(()=>live&&setLoading(false));return()=>{live=false}},[...deps,tick]);return{data,error,loading,reload:()=>setTick(value=>value+1)}}
function Loading({error}:{error?:string}){return <div className="empty"><RefreshCw className="spin" size={20}/><b>{error||"正在整理数据"}</b><span>{error?"检查后端服务后刷新页面":"请稍候"}</span></div>}
function Empty({title,text}:{title:string;text:string}){return <div className="empty"><Library size={24}/><b>{title}</b><span>{text}</span></div>}
function Modal({title,children,onClose,wide=false}:{title:string;children:ReactNode;onClose:()=>void;wide?:boolean}){return createPortal(<div className="modal-backdrop" onMouseDown={onClose}><div className={`modal ${wide?"wide":""}`} onMouseDown={event=>event.stopPropagation()}><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose}><X size={18}/></button></div>{children}</div></div>,document.body)}
function CourseSelect({courses,value,onChange}:{courses:Entity[];value?:any;onChange:(value:string)=>void}){return <select value={value||""} onChange={event=>onChange(event.target.value)} required><option value="">选择课程</option>{courses.map(course=><option key={course.id} value={course.id}>{course.name}</option>)}</select>}
function Status({value}:{value:string}){const labels:Record<string,string>={pending:"待处理",processing:"处理中",success:"已完成",failed:"失败"};return <span className={`status ${value}`}>{labels[value]||value}</span>}

export default function MaterialsPage({ notify }: { notify: (message: string) => void }) {
  const courses = useData(() => api.courses(), []),
    [cid, setCid] = useState<number>(0),
    [view, setView] = useState<Entity | null>(null),
    jobs = useUploadJobs();
  useEffect(() => {
    if (!cid && courses.data?.[0]) setCid(courses.data[0].id);
  }, [courses.data, cid]);
  const mats = useData(
    () => (cid ? api.materials(cid) : Promise.resolve([])),
    [cid],
  );
  const qualityNotice = String(view?.text?.text_preview || "")
    .split("\n")
    .find((line) => line.includes("文本质量提示"));
  const upload = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      await startUpload(cid, form);
      notify("文件上传完成，解析与向量化将在后台继续");
      mats.reload();
      (e.target as HTMLFormElement).reset();
    } catch (x) {
      notify(errorText(x));
    }
  };
  if (courses.loading) return <Loading error={courses.error} />;
  if (!courses.data?.length)
    return <Empty title="请先添加课程" text="资料需要归入一门课程" />;
  return (
    <>
      <div className="split-toolbar">
        <CourseSelect
          courses={courses.data}
          value={cid}
          onChange={(v) => setCid(Number(v))}
        />
        <form className="upload-inline" onSubmit={upload}>
          <input name="title" placeholder="资料标题（选填）" />
          <label className="file-btn">
            <Upload size={15} />
            选择文件
            <input
              name="file"
              type="file"
              accept=".pdf,.docx,.pptx,.txt,.md"
              required
            />
          </label>
          <button className="btn primary" disabled={jobs.some((job) => job.status === "uploading")}>上传</button>
        </form>
      </div>
      {jobs.length > 0 && (
        <div className="upload-queue" aria-live="polite">
          {jobs.map((job) => (
            <article key={job.id} className={job.status}>
              <div><b>{job.name}</b><span>{job.status === "uploading" ? `上传中 ${job.percent}%` : job.status === "processing" ? "已接收，后台解析中" : job.status === "done" ? "上传完成" : job.error || "上传失败"}</span></div>
              <i><em style={{ width: `${job.percent}%` }} /></i>
            </article>
          ))}
        </div>
      )}
      <div className="hint">
        <CircleHelp size={15} />
        支持 PDF、Word、PPT、TXT、Markdown，单个文件不超过 20 MB。
      </div>
      {mats.loading ? (
        <Loading />
      ) : unwrap(mats.data).length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>资料</th>
                <th>类型</th>
                <th>大小</th>
                <th>解析状态</th>
                <th>上传时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {unwrap(mats.data).map((m) => (
                <tr key={m.id}>
                  <td>
                    <button
                      className="link-cell"
                      onClick={async () => {
                        try {
                          const [text, chunks] = await Promise.all([
                            api.materialText(m.id),
                            api.materialChunks(m.id),
                          ]);
                          setView({ ...m, text, chunks });
                        } catch (x) {
                          notify(errorText(x));
                        }
                      }}
                    >
                      <FileText size={17} />
                      <span>
                        <b>{m.title}</b>
                        <small>{m.original_filename}</small>
                      </span>
                    </button>
                  </td>
                  <td>{String(m.file_type).toUpperCase()}</td>
                  <td>{(m.file_size / 1024 / 1024).toFixed(2)} MB</td>
                  <td>
                    <Status value={m.parse_status} />
                  </td>
                  <td>{dateText(m.created_at)}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        className="icon-btn"
                        title="重新解析"
                        onClick={async () => {
                          await api.parseMaterial(m.id);
                          mats.reload();
                          notify("已重新解析");
                        }}
                      >
                        <RefreshCw size={15} />
                      </button>
                      <button
                        className="icon-btn danger"
                        onClick={async () => {
                          if (confirm("删除这份资料？")) {
                            await api.deleteMaterial(m.id);
                            mats.reload();
                            notify("资料已删除");
                          }
                        }}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty
          title="这门课程还没有资料"
          text="上传课件或文档，系统会自动提取文本"
        />
      )}
      {view && (
        <Modal title={view.title} onClose={() => setView(null)} wide>
          <div className="material-detail">
            <div className="detail-actions">
              <button
                className="btn subtle"
                onClick={async () => {
                  await api.rebuildChunks(view.id);
                  notify("文本分块已重建");
                }}
              >
                重建分块
              </button>
              <button
                className="btn primary"
                onClick={async () => {
                  await api.rebuildVectors(view.id);
                  notify("向量索引已重建");
                }}
              >
                建立检索索引
              </button>
            </div>
            <dl className="meta">
              <div>
                <dt>解析状态</dt>
                <dd>{view.parse_status}</dd>
              </div>
              <div>
                <dt>字符数</dt>
                <dd>{view.text?.text_length || 0}</dd>
              </div>
              <div>
                <dt>文本分块</dt>
                <dd>{view.chunks?.total || 0}</dd>
              </div>
            </dl>
            <h3>文本预览</h3>
            {qualityNotice && (
              <div className="material-quality-warning" role="status">
                <CircleHelp size={17} />
                <div>
                  <b>该 PDF 的文本层质量较差</b>
                  <span>{qualityNotice.replace(/^\s*\[?|\]?\s*$/g, "")}</span>
                </div>
              </div>
            )}
            <pre>{view.text?.text_preview || "暂无可预览文本"}</pre>
            <h3>分块内容</h3>
            <div className="chunks">
              {unwrap(view.chunks).map((c: Entity) => (
                <div key={c.id}>
                  <span>
                    #{c.chunk_index + 1}
                    {c.page_no ? ` · 第 ${c.page_no} 页` : ""}
                  </span>
                  <p>{c.content}</p>
                </div>
              ))}
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

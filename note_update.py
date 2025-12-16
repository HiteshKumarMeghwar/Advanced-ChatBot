

# I've just added cookie setting code in config.py



# Add HTTPS terminator + HSTS - pending ( Because of premium domain? )

# AFTER FRONTEND AND PROJECT COMPETE THEN SOME ADVANCE THINGS IN BACKEND .........
# ✔ Captcha
# ✔ Ban system
# ✔ MFA (email)
# ✔ Device fingerprinting
# ✔ IP risk scoring
# ✔ Geo blocking
# ✔ Refresh tokens
# ✔ OAuth2 login
# ✔ WebAuthn
# ✔ Admin security dashboard



# _________________________ FRONTEND _________________________________________

# 1. Project bootstrap

# npx create-next-app@latest chatbot-ui --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
# cd chatbot-ui
# npm i axios js-cookie jwt-decode
# npm i -D @types/js-cookie


# 2. Folder layout (src/*)

# src/
# ├── app/
# │   ├── (auth)/
# │   │   ├── login/
# │   │   │   └── page.tsx
# │   │   ├── register/
# │   │   │   └── page.tsx
# │   │   └── logout/
# │   │       └── route.ts
# │   ├── (chat)/
# │   │   ├── page.tsx                 // /  → redirects to /chat
# │   │   ├── chat/[[...threadId]]/
# │   │   │   └── page.tsx             // /chat or /chat/<threadId>
# │   │   ├── layout.tsx               // shared sidebar
# │   │   └── loading.tsx
# │   ├── api/
# │   │   └── stream/                  // local proxy for /chat/send (optional)
# │   ├── global-error.tsx
# │   └── layout.tsx
# ├── components/
# │   ├── auth/
# │   ├── chat/
# │   ├── common/
# │   └── ui/
# ├── hooks/
# ├── lib/
# │   ├── axios.ts                     // authenticated axios instance
# │   ├── auth.ts                      // login/logout helpers
# │   └── constants.ts
# ├── middleware.ts                    // protect (chat) routes
# └── types/


# 3. ENV (.env.local)

# NEXT_PUBLIC_API_URL=https://api.yourdomain.com
# NEXT_PUBLIC_WS_URL=wss://api.yourdomain.com


# 4. Authenticated Axios instance

# // lib/axios.ts
# import Axios from "axios";
# import Cookie from "js-cookie";

# export const axios = Axios.create({
#   baseURL: process.env.NEXT_PUBLIC_API_URL,
#   headers: { "Content-Type": "application/json" },
# });

# axios.interceptors.request.use((config) => {
#   const token = Cookie.get("access_token");
#   if (token) config.headers.Authorization = `Bearer ${token}`;
#   return config;
# });

# axios.interceptors.response.use(
#   (res) => res,
#   async (err) => {
#     if (err.response?.status === 401) {
#       Cookie.remove("access_token");
#       window.location.href = "/login";
#     }
#     return Promise.reject(err);
#   }
# );



# 5. Auth hooks & helpers

# // lib/auth.ts
# import Cookie from "js-cookie";
# import jwtDecode from "jwt-decode";

# export const setAuth = (token: string) => Cookie.set("access_token", token, { secure: true, sameSite: "strict" });
# export const removeAuth = () => Cookie.remove("access_token");
# export const getMe = () => {
#   const t = Cookie.get("access_token");
#   return t ? (jwtDecode(t) as { sub: string; email: string }) : null;
# };


# 6. Middleware – protect chat zone

# // middleware.ts
# import { NextResponse } from "next/server";
# import type { NextRequest } from "next/server";
# import Cookie from "js-cookie";

# export function middleware(req: NextRequest) {
#   const token = req.cookies.get("access_token")?.value;
#   const isAuthPage = req.nextUrl.pathname.startsWith("/login") || req.nextUrl.pathname.startsWith("/register");

#   if (!token && !isAuthPage) return NextResponse.redirect(new URL("/login", req.url));
#   if (token && isAuthPage) return NextResponse.redirect(new URL("/chat", req.url));
#   return NextResponse.next();
# }

# export const config = { matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"] };



# 7. Login / Register components (very thin)

# // app/(auth)/login/page.tsx
# "use client";
# import { FormEvent } from "react";
# import { axios } from "@/lib/axios";
# import { setAuth } from "@/lib/auth";
# import { useRouter } from "next/navigation";

# export default function Login() {
#   const router = useRouter();
#   async function onSubmit(e: FormEvent<HTMLFormElement>) {
#     e.preventDefault();
#     const fd = new FormData(e.currentTarget);
#     const { data } = await axios.post("/auth/login", {
#       email: fd.get("email"),
#       password: fd.get("password"),
#     });
#     setAuth(data.access_token);
#     router.push("/chat");
#   }
#   return (
#     <form onSubmit={onSubmit} className="grid gap-4 max-w-md mx-auto mt-20">
#       <input name="email" type="email" required placeholder="Email" className="input" />
#       <input name="password" type="password" required placeholder="Password" className="input" />
#       <button className="btn-primary">Login</button>
#     </form>
#   );
# }



# 8. Chat layout (sidebar + outlet)

# // app/(chat)/layout.tsx
# import { Sidebar } from "@/components/chat/Sidebar";
# export default function ChatLayout({ children }: { children: React.ReactNode }) {
#   return (
#     <div className="flex h-screen">
#       <Sidebar />
#       <main className="flex-1 flex flex-col">{children}</main>
#     </div>
#   );
# }


# 9. Thread list (sidebar)

# // components/chat/Sidebar.tsx
# "use client";
# import { axios } from "@/lib/axios";
# import { useEffect, useState } from "react";
# import Link from "next/link";
# import { useParams, useRouter } from "next/navigation";

# export function Sidebar() {
#   const [threads, setThreads] = useState<{ id: string; title: string }[]>([]);
#   const router = useRouter();
#   const { threadId } = useParams();

#   useEffect(() => {
#     axios.get("/threads").then((r) => setThreads(r.data));
#   }, []);

#   async function createThread() {
#     const { data } = await axios.post("/threads", { title: "New thread" });
#     router.push(`/chat/${data.id}`);
#   }

#   return (
#     <aside className="w-64 bg-gray-50 border-r p-4">
#       <button onClick={createThread} className="btn-primary w-full mb-4">+ New thread</button>
#       {threads.map((t) => (
#         <Link key={t.id} href={`/chat/${t.id}`} className={`block p-2 rounded ${threadId === t.id ? "bg-blue-100" : ""}`}>
#           {t.title}
#         </Link>
#       ))}
#     </aside>
#   );
# }



# 10. Chat screen + streaming

# // app/(chat)/chat/[[...threadId]]/page.tsx
# "use client";
# import { axios } as "@/lib/axios";
# import { useEffect, useRef, useState } from "react";
# import { useParams } from "next/navigation";

# type Msg = { role: "user" | "assistant"; content: string };

# export default function ChatPage() {
#   const { threadId } = useParams();
#   const [msgs, setMsgs] = useState<Msg[]>([]);
#   const [input, setInput] = useState("");
#   const abortRef = useRef<AbortController | null>(null);

#   // load history
#   useEffect(() => {
#     if (!threadId) return;
#     axios.get(`/messages/show/${threadId}`).then((r) => setMsgs(r.data));
#   }, [threadId]);

#   // streaming send
#   async function send() {
#     if (!input.trim()) return;
#     const prompt = input;
#     setInput("");
#     setMsgs((m) => [...m, { role: "user", content: prompt }]);

#     abortRef.current = new AbortController();
#     const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/chat/send`, {
#       method: "POST",
#       headers: { "Content-Type": "application/json", Authorization: `Bearer ${Cookie.get("access_token")}` },
#       body: JSON.stringify({ thread_id: threadId, query: prompt }),
#       signal: abortRef.current.signal,
#     });

#     const reader = res.body!.getReader();
#     const decoder = new TextDecoder();
#     let assistant = "";
#     while (true) {
#       const { done, value } = await reader.read();
#       if (done) break;
#       assistant += decoder.decode(value, { stream: true });
#       setMsgs((m) => [...m.slice(0, -1), { role: "assistant", content: assistant }]);
#     }
#   }

#   return (
#     <div className="flex flex-col h-full">
#       <div className="flex-1 overflow-y-auto p-4 space-y-2">
#         {msgs.map((m, i) => (
#           <div key={i} className={`p-2 rounded ${m.role === "user" ? "bg-blue-50 ml-auto" : "bg-gray-100"}`}>
#             {m.content}
#           </div>
#         ))}
#       </div>
#       <div className="p-4 border-t flex gap-2">
#         <input
#           value={input}
#           onChange={(e) => setInput(e.target.value)}
#           onKeyDown={(e) => e.key === "Enter" && send()}
#           className="input flex-1"
#           placeholder="Type a message..."
#         />
#         <button onClick={send} className="btn-primary">Send</button>
#       </div>
#     </div>
#   );
# }




# 11. Delete thread (inline button)

# // inside Sidebar component
# async function deleteThread(id: string) {
#   await axios.delete(`/threads/${id}`);
#   setThreads((t) => t.filter((x) => x.id !== id));
#   if (threadId === id) router.push("/chat");
# }
# ...
# <button onClick={() => deleteThread(t.id)} className="text-red-500 text-xs">Delete</button>



# 12. Profile / logout

# // app/(chat)/profile/page.tsx
# "use client";
# import { removeAuth } from "@/lib/auth";
# import { useRouter } from "next/navigation";

# export default function Profile() {
#   const router = useRouter();
#   function logout() {
#     removeAuth();
#     router.push("/login");
#   }
#   return (
#     <div className="p-8">
#       <h1 className="text-xl font-bold mb-4">Profile</h1>
#       <button onClick={logout} className="btn-danger">Logout</button>
#     </div>
#   );
# }



# 13. Nice-to-have extras (already wired)

# Error boundary (global-error.tsx)
# Loading states (loading.tsx)
# Dark/light theme toggle (read from /users/me/settings)
# Responsive mobile sidebar (Tailwind)
# Type-safe OpenAPI client (openapi-typescript + openapi-fetch)
# Infinite scroll for long threads
# Message status (sending / failed)
# Retry & cancel stream buttons
# File upload drag-zone for RAG documents
# Tool-call disclosure (expand citations)
# SSE fallback if you switch from raw bytes to text/event-stream
# Web-socket real-time presence (who is online)



# 14. Next steps

# npm run dev → everything works locally.
# docker build -t chatbot-ui . – multi-stage image (output < 50 MB).
# Push to GitHub → trigger GitHub Actions (lint, test, build, push to registry).
# Deploy container behind Traefik + Let’s-Encrypt.
# Connect Next-JS via env-vars to https://api.yourdomain.com.
# ACS + Azure Voice Live control demo

This sample demonstrates two ways to run a low-latency Azure Voice Live agent:

1. **Browser voice chat**: microphone audio streams from a web page to the backend, then to Azure Voice Live. This does not need an ACS phone number.
2. **ACS telephony bridge**: Azure Communication Services (ACS) Call Automation answers calls, opens bidirectional media streaming, and bridges 24 kHz PCM audio to Azure Voice Live.

The default agent is a voice-control assistant for a fictional smart home. The browser demo includes a live context editor so a presenter can change what the agent knows before or during a session, plus a simulated tool-result injection path for demos.

The deployed sample also includes **demo-only fake healthcare tools** for appointment lookup, medical result lookup, human escalation, and prescription requests. They return synthetic data only and are not connected to any clinical system.

## How it works

```text
Browser mic ──WebSocket──┐
                         │
                         ├── FastAPI bridge ──WebSocket── Azure Voice Live API
ACS call ──ACS media WS──┘
```

### Browser voice path

- `GET /voice` serves the web demo UI.
- The browser captures microphone audio with `getUserMedia`.
- Audio is converted to 24 kHz, 16-bit PCM, base64 encoded, and sent to `wss://<host>/ws/browser-voice`.
- The backend forwards audio chunks to Azure Voice Live as `input_audio_buffer.append` events.
- Voice Live response audio deltas are streamed back to the browser and played immediately.

### Dynamic demo context

The `/voice` page has a **Conversation prompt/context** editor:

- **Before the session**: edit the context and click **Start voice session**. The UI sends the context as soon as the WebSocket opens.
- **During the session**: edit the context and click **Apply context to live session**. The backend sends a new `session.update` to Voice Live with the latest context appended to the base system instructions.
- **Fake tool result**: click **Inject as fake tool result**. The backend inserts a live conversation item that looks like external state from a simulated tool named `demo_state_editor`, then asks Voice Live to respond.

This is useful for demos where you want to reveal changing application state to the agent without building real integrations.

### Fake medical tools

Voice Live receives five callable function tools in `session.update`:

| Tool | Purpose |
|---|---|
| `get_doctor_calendar` | Returns fake appointment slots by specialty/date/urgency. |
| `book_appointment` | Books a fake appointment into the in-memory fake system and marks the chosen slot booked. |
| `get_medical_results` | Returns fake test results such as bloods, cholesterol, or X-ray. |
| `escalate_to_person` | Creates a fake human callback/escalation ticket. |
| `request_prescription` | Creates a fake prescription request queued for clinician review. |

When Voice Live emits a function-call event, the backend:

1. Parses the function name and JSON arguments.
2. Calls the matching fake API function in `app/fake_medical_tools.py`.
3. Sends a `conversation.item.create` event with `type: function_call_output`.
4. Sends `response.create` so the agent explains the result to the user.

All fake tool responses include a demo disclaimer. The app does not store patient data.

### ACS telephony path

- `POST /api/incoming-call` receives ACS Event Grid incoming call events.
- The app answers the call with bidirectional ACS media streaming enabled.
- ACS connects to `wss://<host>/ws/acs-media`.
- ACS audio packets are forwarded to Voice Live.
- Voice Live audio deltas are returned to ACS so they play into the call.

ACS PSTN calling still requires an acquired/assigned ACS phone number.

## Azure resources created

The current deployed demo uses:

| Resource | Value |
|---|---|
| Resource group | `rg-voice-live-acs-demo` |
| ACS resource | `vlacs81175250` |
| Voice Live / AI resource | `vlai81175250` |
| Voice Live endpoint | `https://vlai81175250.cognitiveservices.azure.com/` |

## AKS hosting

The app is deployed to the existing AKS cluster and existing nginx ingress/LB:

| Resource | Value |
|---|---|
| AKS cluster | `picowal-cluster` in `tileforge-rg` |
| Namespace | `voice-live-demo` |
| Image | `tileforgeacr.azurecr.io/voice-live-acs-demo` |
| Public URL / merged console | `https://voice-live-acs.demos.wavefunctionlabs.com` |
| ACS incoming webhook | `https://voice-live-acs.demos.wavefunctionlabs.com/api/incoming-call` |
| ACS media WebSocket | `wss://voice-live-acs.demos.wavefunctionlabs.com/ws/acs-media` |
| Browser voice chat alias | `https://voice-live-acs.demos.wavefunctionlabs.com/voice` |
| Fake systems GUI | `https://voice-live-acs.demos.wavefunctionlabs.com/systems` |
| Route/service mappings | `https://voice-live-acs.demos.wavefunctionlabs.com/api/routes` |
| Fake API index | `https://voice-live-acs.demos.wavefunctionlabs.com/api/fake` |

The image was built by a one-shot Kubernetes build job on the existing ARM64 AKS nodes and pushed to the existing `tileforgeacr` registry. No new load balancer or persistent compute was created.

The browser voice chat includes a custom greeting box, patient identity fields, and live context editor. Demo users identify with name, date of birth, and the last four digits of their registered fake phone number. Each browser voice session randomly chooses an en-GB Azure voice and personalizes the greeting with the linked synthetic patient's name. The greeting is spoken when the session starts and can be replayed during the call. Greeting and context can be saved into the in-memory demo configuration. Apply context before or during a voice session to update the Voice Live instructions, or inject the same context as a simulated tool result for demos.

The main `/voice` page is a merged tabbed console with **Voice chat** and **Fake systems** tabs. The standalone tabbed fake systems GUI remains available at `/systems` and lets a presenter shape the demo live:

- Add synthetic patients that can be verified and linked in the voice session.
- Add doctor calendar slots that the `get_doctor_calendar` tool can return.
- Show booked appointments created by the `book_appointment` tool or the control panel.
- Add synthetic medical results that the `get_medical_results` tool can return.
- Create fake escalation callback tickets.
- Create fake prescription requests.
- Reset the in-memory demo state back to defaults.
- Inspect the raw in-memory state that the Voice Live tools can see.
- Open a patient view showing the selected synthetic patient profile plus linked results, escalations, and prescription requests.

The state is intentionally in-memory and demo-only. It is shared by the browser GUI, REST APIs, and Voice Live tools while the pod is running.

## Configuration

Use `.env.example` as the template:

| Variable | Purpose |
|---|---|
| `ACS_CONNECTION_STRING` | ACS connection string for answering/creating calls. Keep this secret. |
| `ACS_ENDPOINT` | Optional keyless ACS endpoint alternative. |
| `VOICE_LIVE_ENDPOINT` | Azure AI/Voice Live endpoint. |
| `VOICE_LIVE_API_KEY` | Optional API key for Voice Live. Keep this secret. If omitted, the app uses `DefaultAzureCredential`. |
| `VOICE_LIVE_MODEL` | Voice Live model, for example `gpt-realtime-mini`. |
| `VOICE_LIVE_VOICE` | Azure TTS voice name. Defaults to British English `en-GB-SoniaNeural`. |
| `VOICE_LIVE_INSTRUCTIONS` | Base system prompt for the agent. |
| `PUBLIC_HOST` | Public HTTPS URL used for ACS callbacks and browser WebSockets. |
| `ACS_PHONE_NUMBER` | Optional E.164 ACS number for outbound calls. |

## Run locally

1. Create `.env` from `.env.example`, or use the generated local values if present:

   ```bash
   cp .env.example .env
   ```

2. Set `PUBLIC_HOST` to a public HTTPS tunnel URL that forwards to local port `8080`.

3. Start the app:

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

4. Open the browser voice demo:

   ```text
   http://localhost:8080/
   ```

5. Register ACS incoming call events once the public URL is live:

   ```bash
   RESOURCE_GROUP=rg-voice-live-acs-demo \
   ACS_NAME=vlacs81175250 \
   PUBLIC_HOST=https://your-public-host.example \
   ./scripts/create-event-subscription.sh
   ```

## Telephony notes

ACS can only receive/place PSTN calls after a phone number is acquired and assigned, which can require portal/regulatory steps. After that, set `ACS_PHONE_NUMBER=+...` to enable `POST /api/calls/outbound/{target_phone_number}`.

For inbound calls, point the ACS Event Grid subscription at:

```text
https://<public-host>/api/incoming-call
```

## Deploy to an existing AKS cluster

The sample includes Kubernetes manifests in `k8s/`:

- `namespace.yaml`
- `deployment.yaml`
- `service.yaml`
- `ingress.yaml`

For the lowest extra cost, reuse an existing cluster, registry, ingress controller, load balancer, and DNS zone. The current deployment uses:

- Existing AKS nodes
- Existing Basic ACR
- Existing nginx ingress controller
- Existing public load balancer IP
- Existing cert-manager issuer

Build on the cluster with a one-shot Kaniko job or another in-cluster builder, push the image to the existing ACR, then update the deployment image:

```bash
kubectl -n voice-live-demo set image deployment/voice-live-acs-demo \
  app=tileforgeacr.azurecr.io/voice-live-acs-demo:<tag>
kubectl -n voice-live-demo rollout status deployment/voice-live-acs-demo
```

Create the runtime secret from an env file:

```bash
kubectl -n voice-live-demo create secret generic voice-live-acs-demo-env \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Useful endpoints

| Endpoint | Purpose |
|---|---|
| `/` | Merged browser voice and fake systems demo console. |
| `/api/routes` | JSON metadata showing configured callback/WebSocket URLs and service mappings. |
| `/healthz` | Health probe. |
| `/voice` | Browser voice chat UI alias for the merged console. |
| `/systems` | Fake healthcare systems control panel. |
| `/ws/browser-voice` | Browser voice WebSocket. |
| `/api/incoming-call` | ACS incoming call Event Grid webhook. |
| `/api/callbacks` | ACS Call Automation callback endpoint. |
| `/ws/acs-media` | ACS bidirectional media WebSocket. |
| `/api/calls/outbound/{target}` | Optional outbound PSTN call endpoint, requires `ACS_PHONE_NUMBER`. |
| `/api/fake` | Index of fake medical APIs. |
| `/api/fake/state` | Current in-memory fake system state. |
| `/api/fake/reset` | Reset fake system state to defaults. |
| `/api/fake/verify-patient` | Verify fake user identity by name, DOB, and phone last-4. |
| `/api/fake/doctor-calendar` | Fake doctor calendar lookup. |
| `/api/fake/appointments` | Fake appointment booking API. |
| `/api/fake/medical-results` | Fake medical results lookup. |
| `/api/fake/escalate` | Fake human escalation callback request. |
| `/api/fake/prescription-request` | Fake prescription request. |

## Cleanup

Remove the AKS workload:

```bash
kubectl delete namespace voice-live-demo
```

Remove the demo Azure resource group:

```bash
az group delete --name rg-voice-live-acs-demo --yes
```

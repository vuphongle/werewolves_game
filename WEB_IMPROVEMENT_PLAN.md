# Kế hoạch cải tiến Werewolves Game trên Web

> Trạng thái: Bản nháp để lập kế hoạch  
> Phạm vi: Web desktop  
> Ngoài phạm vi: Cải tiến ứng dụng Android, UI native và tối ưu giao diện mobile  
> Nguyên tắc triển khai: Sửa tính đúng đắn của luật chơi trước, sau đó cải thiện UX và cuối cùng mới tích hợp voice chat.

## 1. Mục tiêu

Kế hoạch này hướng tới bốn kết quả chính:

1. Bộ vai hiển thị ở phòng chờ phải giống hoàn toàn với bộ vai được chia khi bắt đầu.
2. Người chơi luôn biết ván đang ở pha nào, cần làm gì và hành động đã được ghi nhận hay chưa.
3. Quản trò có thể cấu hình và điều hành ván chơi mà không phải hiểu các chi tiết kỹ thuật nội bộ.
4. Chế độ chơi từ xa có voice chat theo đúng pha và phe, không làm lộ vai.

## 2. Phạm vi

### Trong phạm vi

- Backend Flask/Flask-SocketIO và game engine.
- Giao diện web desktop ở phòng đăng nhập, phòng chờ và màn hình chơi.
- Logic dựng bộ vai, chia vai và kiểm tra điều kiện thắng.
- Chat chữ, nhật ký ván chơi và trạng thái kết nối.
- Voice chat audio-only trên web.
- Kiểm thử tự động cho luật chơi và các luồng web quan trọng.
- Bảo mật các thao tác quản trị liên quan trực tiếp đến ván chơi.

### Ngoài phạm vi

- Viết lại ứng dụng Android hoặc thêm giao diện chơi native.
- Tối ưu riêng cho màn hình điện thoại.
- Video call, chia sẻ màn hình hoặc ghi âm.
- Hệ thống tài khoản người dùng.
- Matchmaking công khai.
- Nhiều phòng chơi đồng thời trong cùng một tiến trình server, trừ khi được tách thành dự án riêng.

Ứng dụng Android tiếp tục giữ vai trò bật/tắt server và hiển thị địa chỉ truy cập. Mọi tính năng gameplay mới được xây dựng trên web.

## 3. Các vấn đề hiện tại cần giải quyết

### P0 — Logic và bảo mật

- `Seer` đang được chọn mặc định trên UI nhưng bị loại khỏi danh sách khi backend dựng bộ vai.
- Logic tính bộ vai bị lặp giữa JavaScript và Python, nên bản xem trước có thể khác kết quả thực tế.
- Nút chọn vai ngẫu nhiên dùng tổng `rating` gần 0 nhưng chưa xét số người, tương tác giữa vai và điều kiện thắng.
- Điều kiện thắng của phe Dân làng có thể kết thúc ván trong khi vai thù địch trung lập như Serial Killer vẫn còn sống.
- Client có thể gửi `start_game` với mode `pass_and_play` để vượt một phần kiểm tra quyền quản trò.
- Endpoint `/shutdown` chưa yêu cầu quyền quản trị.

### P1 — Luồng chơi và giao tiếp

- Pha thảo luận và pha chỉ điểm đang gộp chung; người chơi có thể bỏ phiếu trước khi cuộc thảo luận thực sự diễn ra.
- Phiếu chỉ điểm được công bố ngay, dễ tạo hiệu ứng bỏ phiếu theo đám đông.
- Người chơi không thể đổi lựa chọn trước khi khóa phiếu.
- Ban đêm không có kênh phối hợp riêng cho phe Sói.
- Nhật ký công khai, thông tin riêng và thông báo hệ thống chưa được phân tách rõ.
- Trạng thái mất kết nối mới chỉ được ghi log, chưa được biểu diễn rõ trên danh sách người chơi.

### P1 — UI/UX web desktop

- Phòng chờ dài và chứa quá nhiều tùy chọn cùng lúc.
- Thẻ vai hiển thị chi tiết bằng hover và lộ thông tin kỹ thuật như `priority`.
- Bản tóm tắt vai chưa phải là kết quả được backend xác nhận.
- Nút bắt đầu ván không luôn đi kèm cảnh báo và trạng thái sẵn sàng.
- Màn hình chơi chưa phân cấp đủ rõ giữa pha hiện tại, hành động chính, chat và lịch sử.
- Phản hồi sau khi gửi hành động chưa cho biết còn đang chờ bao nhiêu người.

## 4. Nguyên tắc thiết kế

1. **Server là nguồn dữ liệu duy nhất:** Browser không tự quyết định bộ vai, người thắng hoặc quyền truy cập voice.
2. **Bản xem trước phải chính xác:** Bộ vai được duyệt ở lobby phải chính là bộ vai được chia.
3. **Công khai và riêng tư phải tách biệt:** Mọi payload, log và voice room đều phải có phạm vi rõ ràng.
4. **Ưu tiên hành động hiện tại:** Mỗi pha chỉ nên có một hành động chính nổi bật.
5. **Không tự mở microphone:** Người dùng phải chủ động cấp quyền và bật mic.
6. **Voice không được chặn gameplay:** Mất voice vẫn phải chơi được bằng chat chữ và UI.
7. **Tính năng mới có feature flag:** Có thể tắt nhanh mà không ảnh hưởng ván chơi hiện tại.

## 5. Kiến trúc mục tiêu

### 5.1 Dựng bộ vai

Tạo một thành phần backend duy nhất, ví dụ `RoleDeckBuilder`, nhận:

```text
player_count
selected_special_roles
preset
game_options
optional_random_seed
```

Và trả về:

```text
exact_deck
team_counts
balance_score
complexity_score
warnings
errors
```

Frontend chỉ gửi ý định cấu hình và hiển thị kết quả mà backend trả về. Không tiếp tục duy trì một bản tính số Sói độc lập trong JavaScript.

### 5.2 Mô hình điều kiện thắng

Chuẩn hóa metadata cho từng vai hoặc phe:

```text
wins_with_team
has_solo_win
blocks_village_win
blocks_werewolf_win
continues_after_personal_win
```

Việc kiểm tra thắng nên trả về danh sách kết quả có cấu trúc thay vì chỉ ghi một chuỗi `winner`:

```text
winning_players
winning_teams
primary_reason
personal_wins
game_should_end
```

### 5.3 Luồng pha đề xuất

```text
Lobby
  -> Night
  -> DawnResult
  -> DayDiscussion
  -> Nomination
  -> LynchVote
  -> Night hoặc GameOver
```

`Defense` có thể được thêm sau giữa `Nomination` và `LynchVote` nếu nhóm chơi thực sự cần một khoảng biện hộ riêng.

### 5.4 Voice chat

Voice chạy như một dịch vụ media riêng. Flask chỉ xác thực người chơi, phát token và điều phối quyền theo pha.

Các voice channel logic:

```text
Lobby: tất cả người chơi
Day: người còn sống
Night/Wolves: chỉ phe Sói được phép nói và nghe
Ghost: người đã chết
GameOver: tất cả người chơi
```

Không dùng mã game công khai làm tên voice room. Mỗi ván cần một UUID nội bộ không thể đoán.

## 6. Roadmap triển khai

Quy ước effort tương đối:

- **S:** Thay đổi nhỏ, phạm vi rõ.
- **M:** Chạm nhiều file hoặc cần kiểm thử tích hợp.
- **L:** Một nhóm chức năng hoàn chỉnh.
- **XL:** Cần tách thành nhiều ticket trước khi triển khai.

### Giai đoạn 0 — Chốt luật và dựng baseline

Mục tiêu: Thống nhất hành vi mong muốn trước khi sửa game engine.

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| RULE-001 | Viết ma trận số Sói theo số người | S | Không |
| RULE-002 | Xác định vai nào là filler, special và neutral-hostile | S | Không |
| RULE-003 | Chốt luật thắng của Serial Killer, Monster, Fool và Demented Villager | M | Không |
| RULE-004 | Chốt luật hòa phiếu, quyền Trưởng làng và quyền đổi phiếu | M | Không |
| RULE-005 | Chọn open vote, secret vote hoặc cho phép quản trò cấu hình | S | Không |
| TEST-001 | Ghi lại các kịch bản gameplay hiện tại làm baseline | M | RULE-001..005 |

Tiêu chí hoàn thành:

- Có một tài liệu luật ngắn làm nguồn tham chiếu.
- Không còn câu hỏi mở về việc một vai trung lập có chặn chiến thắng của phe hay không.
- Có danh sách bộ vai mẫu cho ít nhất 4, 6, 8, 10 và 12 người.

### Giai đoạn 1 — Sửa logic chia vai và quyền quản trị

Mục tiêu: Đảm bảo ván chơi bắt đầu với đúng bộ vai và không thể vượt quyền.

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| DECK-001 | Tạo `RoleDeckBuilder` phía backend | L | Giai đoạn 0 |
| DECK-002 | Sửa lỗi vai `Seer` mặc định bị loại | S | DECK-001 |
| DECK-003 | Tạo API preview/validate bộ vai | M | DECK-001 |
| DECK-004 | Xóa phép tính bộ vai trùng lặp khỏi frontend | M | DECK-003 |
| DECK-005 | Thêm preset Cơ bản, Tiêu chuẩn và Nâng cao | M | DECK-001 |
| WIN-001 | Chuẩn hóa kết quả thắng theo cấu trúc | L | RULE-003 |
| AUTH-001 | Mọi lệnh bắt đầu ván phải xác thực quản trò ở server | S | Không |
| AUTH-002 | Bảo vệ hoặc loại bỏ endpoint `/shutdown` khỏi web public | S | Không |
| TEST-002 | Unit test dựng bộ vai theo số người | M | DECK-001 |
| TEST-003 | Unit test điều kiện thắng và vai trung lập | L | WIN-001 |

Tiêu chí nghiệm thu:

- Số vai được chia luôn bằng số người chơi.
- Mọi vai được backend xác nhận trong `exact_deck` đều xuất hiện đúng số lượng.
- UI không thể hiển thị Seer nếu backend không định chia Seer.
- Không client thường nào bắt đầu, chuyển pha, dừng server hoặc thay đổi cấu hình quản trị được.
- Các test bao phủ tối thiểu các mốc 4, 6, 8, 10 và 12 người.

### Giai đoạn 2 — Làm lại phòng chờ web desktop

Mục tiêu: Giảm mật độ thông tin và giúp quản trò kiểm tra ván trước khi bắt đầu.

Cấu trúc đề xuất:

```text
Header: Mã phòng + trạng thái server + nút sao chép

Cột trái:
- Danh sách người chơi
- Chat phòng chờ

Cột giữa:
- Preset vai
- Danh sách vai đã chọn
- Tìm kiếm/lọc theo phe và độ khó

Cột phải:
- Cấu hình ván
- Bộ bài chính xác
- Cảnh báo
- Nút Bắt đầu ván
```

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| LOBBY-001 | Thiết kế lại bố cục desktop ba vùng | L | DECK-003 |
| LOBBY-002 | Hiển thị bộ bài chính xác từ backend | M | DECK-003 |
| LOBBY-003 | Thêm preset và nút tạo lại bộ vai | M | DECK-005 |
| LOBBY-004 | Thêm bộ lọc phe, độ khó và tìm kiếm vai | M | Không |
| LOBBY-005 | Mở chi tiết vai bằng panel/modal thay vì chỉ hover | M | Không |
| LOBBY-006 | Ẩn priority kỹ thuật khỏi người chơi phổ thông | S | Không |
| LOBBY-007 | Thêm trạng thái Ready/Warning/Error cạnh nút bắt đầu | S | DECK-003 |
| LOBBY-008 | Thay `alert`/`confirm` bằng toast và dialog thống nhất | M | Không |

Tiêu chí nghiệm thu:

- Quản trò nhìn thấy toàn bộ bộ bài cuối cùng mà không phải tự tính.
- Không thể bắt đầu nếu cấu hình có lỗi.
- Cảnh báo không chặn ván phải được phân biệt với lỗi bắt buộc sửa.
- Người chơi không phải quản trò chỉ xem được cấu hình, không sửa được.

### Giai đoạn 3 — Cải thiện màn hình chơi và giao tiếp chữ

Mục tiêu: Làm rõ trạng thái ván, hành động và kênh thông tin.

Bố cục desktop đề xuất:

```text
Header cố định: Pha | Đồng hồ | Trạng thái voice

Cột trái:
- Nhật ký công khai
- Chat phù hợp với kênh hiện tại

Trung tâm:
- Hành động của pha hiện tại
- Xác nhận, thay đổi hoặc hủy lựa chọn
- Trạng thái đang chờ

Cột phải:
- Vai của tôi
- Danh sách người chơi
- Trạng thái sống/chết/kết nối
- Điều khiển quản trò nếu có
```

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| FLOW-001 | Thêm pha `DayDiscussion` tách khỏi `Nomination` | L | RULE-004 |
| FLOW-002 | Cho phép đổi lựa chọn trước khi khóa pha | M | FLOW-001 |
| FLOW-003 | Thêm chế độ phiếu công khai/kín theo cấu hình | L | RULE-005 |
| FLOW-004 | Hiển thị `đã hành động / đang chờ N người` | M | Không |
| FLOW-005 | Thêm bước xác nhận cho hành động gây chết hoặc khóa phiếu | M | Không |
| COMMS-001 | Tách Public Log, Private Intel và System Events | L | Không |
| COMMS-002 | Thêm trạng thái online/disconnected/reconnecting | M | Không |
| COMMS-003 | Cho quản trò xử lý người rời ván | M | COMMS-002 |
| UI-001 | Thiết kế lại bố cục màn hình chơi desktop | L | FLOW-001 |
| UI-002 | Chuẩn hóa toast, dialog và thông báo lỗi | M | LOBBY-008 |
| UI-003 | Thêm keyboard focus và điều khiển không phụ thuộc màu sắc | M | UI-001 |

Tiêu chí nghiệm thu:

- Mỗi pha chỉ có một CTA chính rõ ràng.
- Người chơi biết lựa chọn hiện tại và có thể thay đổi trước khi bị khóa.
- Thông tin riêng không xuất hiện trong log công khai hoặc payload của người khác.
- Mất kết nối và kết nối lại không làm mất vai hoặc phiếu đã gửi.

### Giai đoạn 4 — Voice chat web audio-only

Mục tiêu: Thêm voice cho chơi từ xa mà không làm lộ phe hoặc phụ thuộc vào Android.

#### Quyết định kiến trúc cần chốt

- MVP thử nghiệm bằng Jitsi hay triển khai thẳng LiveKit.
- Dùng LiveKit Cloud hay self-host.
- Voice room tách vật lý theo phe/pha hay dùng một room với chính sách quyền động.
- Voice có bắt buộc không, hay luôn cho phép chơi text-only.

Khuyến nghị hiện tại: LiveKit audio-only, room tách theo phạm vi nghe và token do Flask phát.

#### Điều kiện hạ tầng bắt buộc

- Web gameplay phải chạy bằng HTTPS. Trình duyệt chỉ cho `getUserMedia()` truy cập microphone trong secure context; `http://<LAN-IP>` thông thường sẽ không đủ điều kiện.
- Media server chạy riêng với game server/Android host.
- Có STUN/TURN hoặc dịch vụ media xử lý kết nối qua NAT.
- Không lưu API secret hoặc media token trong JavaScript tĩnh.

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| VOICE-001 | Viết ADR chọn Jitsi/LiveKit và Cloud/self-host | M | Không |
| VOICE-002 | Chuẩn hóa HTTPS cho môi trường triển khai web | L | VOICE-001 |
| VOICE-003 | Tạo feature flag `ENABLE_VOICE_CHAT` | S | Không |
| VOICE-004 | Tạo endpoint phát token ngắn hạn dựa trên session | L | VOICE-001 |
| VOICE-005 | Tạo voice policy theo phase/team/alive state | L | FLOW-001 |
| VOICE-006 | Tích hợp SDK audio vào giao diện web | L | VOICE-004 |
| VOICE-007 | UI bật/tắt mic, trạng thái kết nối và active speaker | L | VOICE-006 |
| VOICE-008 | Phòng Sói ban đêm và phòng hồn ma | L | VOICE-005..007 |
| VOICE-009 | Quyền quản trò: mute, kick voice và mute all | M | VOICE-004 |
| VOICE-010 | Xử lý reconnect và fallback text-only | L | VOICE-006 |
| VOICE-011 | Kiểm thử chống vào sai phòng bằng token hoặc client giả | M | VOICE-004..008 |

Tiêu chí nghiệm thu:

- Không người chơi nào nghe được kênh không thuộc quyền của họ.
- Token không cho client tự chọn game, phe hoặc room.
- Chuyển pha không tự động bật microphone.
- Mất voice không làm mất kết nối Socket.IO hoặc chặn hành động game.
- Người dùng từ chối quyền microphone vẫn chơi được đầy đủ bằng text.
- Quản trò có thể tắt voice toàn ván bằng feature/config flag.

### Giai đoạn 5 — Hoàn thiện trải nghiệm web

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| UX-001 | Âm báo chuyển pha, gần hết giờ và tới lượt | M | UI-001 |
| UX-002 | Cài đặt âm lượng, tắt âm và giảm chuyển động | M | VOICE-007 |
| UX-003 | Rà soát độ tương phản và trạng thái focus | M | UI-001 |
| UX-004 | Hoàn thiện nội dung PG hoặc đổi tên option cho đúng phạm vi | M | Không |
| UX-005 | Tutorial ngắn cho quản trò lần đầu | M | LOBBY-001 |
| UX-006 | Màn hình tổng kết: timeline, vai và các personal win | L | WIN-001 |

### Giai đoạn 6 — Phát hành và vận hành

| ID | Công việc | Effort | Phụ thuộc |
|---|---|---:|---|
| OPS-001 | Cập nhật Docker Compose cho dịch vụ voice đã chọn | L | VOICE-001 |
| OPS-002 | Cập nhật nginx, TLS và WebSocket proxy | M | VOICE-002 |
| OPS-003 | Bổ sung health check cho game và voice service | M | OPS-001 |
| OPS-004 | Ghi log lỗi có cấu trúc, không ghi nội dung voice | M | Không |
| OPS-005 | Cập nhật README và hướng dẫn rollback | M | Các giai đoạn trước |
| OPS-006 | Phát hành beta với voice mặc định tắt | S | Giai đoạn 4 |

## 7. Kế hoạch sprint gợi ý

Không gắn số ngày cố định trước khi chốt luật và nguồn lực. Có thể tổ chức thành các sprint theo kết quả:

### Sprint 1 — Correctness

- RULE-001..005
- DECK-001..004
- AUTH-001..002
- TEST-002

Kết quả: Bộ vai UI và backend thống nhất; các lệnh quản trị không thể bị vượt quyền.

### Sprint 2 — Win conditions và lobby

- WIN-001
- TEST-003
- DECK-005
- LOBBY-001..007

Kết quả: Quản trò có preset, exact deck và cảnh báo rõ trước khi bắt đầu.

### Sprint 3 — Game flow

- FLOW-001..005
- COMMS-001..003
- UI-001..003

Kết quả: Luồng ngày/đêm rõ ràng, có xác nhận hành động và trạng thái chờ.

### Sprint 4 — Voice foundation

- VOICE-001..007
- VOICE-010

Kết quả: Voice chung có xác thực, HTTPS và fallback text-only.

### Sprint 5 — Voice theo luật chơi

- VOICE-008..011
- OPS-001..003

Kết quả: Kênh Sói/hồn ma hoạt động an toàn theo pha và phe.

### Sprint 6 — Polish và beta

- UX-001..006
- OPS-004..006

Kết quả: Có bản beta có thể bật voice theo feature flag và rollback an toàn.

## 8. Chiến lược kiểm thử

### Unit test

- Dựng bộ vai cho các mốc người chơi khác nhau.
- Số Sói thường và Sói đặc biệt.
- Vai bắt buộc, filler và giới hạn số lượng.
- Từng điều kiện thắng phe và thắng cá nhân.
- Chuỗi tử vong: người yêu, Hunter, Honeypot, armor và poison.
- Hòa phiếu, Trưởng làng và Lawyer.

### Integration test

- Tạo lobby, tham gia, chuyển quản trò và bắt đầu ván.
- Reload/reconnect ở từng pha.
- Gửi hành động hai lần hoặc sau khi pha đã khóa.
- Client thường thử gọi các event quản trị.
- Thông tin riêng không xuất hiện trong payload công khai.
- Rematch giữ hoặc reset đúng cấu hình dự kiến.

### Voice test

- Cho phép/từ chối microphone.
- Mất mạng và kết nối lại.
- Người sống không nghe phòng hồn ma.
- Dân làng không nghe phòng Sói ban đêm.
- Người chơi sửa room/token từ DevTools không vào được phòng khác.
- Chuyển pha liên tục không để lại audio track cũ.
- Voice server lỗi nhưng gameplay vẫn tiếp tục.

### Ma trận trình duyệt desktop

- Chrome/Chromium.
- Microsoft Edge.
- Firefox.
- Safari desktop nếu có người dùng macOS.

## 9. Rủi ro và cách giảm thiểu

| Rủi ro | Ảnh hưởng | Giảm thiểu |
|---|---|---|
| Thay luật làm hỏng vai phức tạp | Cao | Chốt RULE và viết test trước khi refactor |
| UI và backend tiếp tục lệch bộ vai | Cao | Chỉ backend được dựng exact deck |
| Voice làm lộ phe | Rất cao | Room/token do server quyết định; test client giả |
| Microphone không chạy trên LAN HTTP | Cao | Bắt buộc HTTPS hoặc tắt voice với cảnh báo rõ |
| Media server quá tải | Trung bình | Audio-only, feature flag và giám sát health |
| Voice lỗi làm chặn ván | Cao | Tách kết nối media khỏi Socket.IO; luôn có text fallback |
| Scope voice phình thành video conference | Cao | Khóa phạm vi audio-only, không recording/video |
| Refactor quá lớn trong một lần | Cao | Chia theo milestone và giữ feature flag |

## 10. Definition of Done chung

Một ticket chỉ được coi là hoàn thành khi:

- Có tiêu chí nghiệm thu đã được kiểm tra.
- Có test tự động tương ứng nếu ticket thay đổi luật hoặc quyền hạn.
- Không đưa thông tin vai riêng vào payload/log công khai.
- Chuỗi dịch của tất cả locale vẫn khớp key và placeholder.
- Không thêm literal giao diện mới trực tiếp vào JavaScript/Python nếu nội dung cần dịch.
- README hoặc tài liệu cấu hình được cập nhật nếu có biến môi trường mới.
- Có cách tắt hoặc rollback đối với thay đổi hạ tầng/voice.

## 11. Các quyết định cần chốt trước khi bắt đầu

- [ ] Luật thắng chính xác của từng vai trung lập.
- [ ] Bộ vai preset cho từng số lượng người chơi.
- [ ] Phiếu chỉ điểm công khai hay bí mật.
- [ ] Có thêm pha biện hộ riêng hay không.
- [ ] Có cho đổi phiếu trước khi khóa không.
- [ ] Voice là tùy chọn theo từng ván hay cấu hình toàn server.
- [ ] Jitsi hay LiveKit.
- [ ] Cloud hay self-host cho voice.
- [ ] Cách cung cấp HTTPS cho các máy truy cập từ mạng LAN.
- [ ] Trình duyệt desktop nào được hỗ trợ chính thức.

## 12. Tài liệu kỹ thuật tham khảo

- LiveKit token và quyền phòng: <https://docs.livekit.io/home/server/generating-tokens>
- LiveKit self-hosting: <https://docs.livekit.io/transport/self-hosting/>
- Jitsi IFrame API: <https://jitsi.github.io/handbook/docs/dev-guide/dev-guide-iframe/>
- WebRTC/STUN/TURN: <https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Protocols>
- Yêu cầu HTTPS khi truy cập microphone: <https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia>


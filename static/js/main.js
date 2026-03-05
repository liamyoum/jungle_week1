$(document).ready(function () {
    // 1. 뒤로가기 캐시(bfcache) 방지: 뒤로가기로 왔을 때 타이머 꼬임 방지
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) {
            window.location.reload();
        }
    });

    const clientStartTime = sessionStorage.getItem('clientStartTime');
    const serverStartTime = sessionStorage.getItem('serverStartTime');
    const pastTime = sessionStorage.getItem('pastTime');

    if (clientStartTime && serverStartTime) {
        //[상태 A] 새로고침 했는데 현재 '공부 중'인 경우
        const accumulated = parseInt(pastTime) || 0;
        let timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
            <p class="text-3xl font-black text-green-700">${serverStartTime}</p>
            <h2 class="text-m font-bold text-gray-400 tracking-widest mt-1 mb-1">지금까지 이만큼 공부했어요</h2>
            <p id="stopwatch-display" class="text-3xl font-black text-green-700">00:00:00</p>`;

        $('#start-time-display').html(timehtml);
        $('#start-btn').addClass('hidden');
        $('#pause-btn').removeClass('hidden').text('휴식');
        $('#end-btn').removeClass('hidden');
        $('#btn-container').removeClass('justify-center').addClass('justify-between');

        startStopwatch(clientStartTime, accumulated);

    } else if (pastTime) {
        //[상태 B] 새로고침 했는데 현재 '휴식 중'인 경우 (이 부분이 없어서 0으로 초기화 됐었음!)
        const accumulated = parseInt(pastTime) || 0;
        let timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
            <p class="text-3xl font-black text-gray-400">휴식 중</p>
            <h2 class="text-m font-bold text-gray-400 tracking-widest mt-1 mb-1">지금까지 이만큼 공부했어요</h2>
            <p id="stopwatch-display" class="text-3xl font-black text-green-700">${formatTime(accumulated)}</p>`;

        $('#start-time-display').html(timehtml);
        $('#start-btn').addClass('hidden');
        $('#pause-btn').removeClass('hidden').text('재개')
            .removeClass('border-green-300 bg-green-500/80 hover:bg-red-500/30')
            .addClass('border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30');
        $('#end-btn').removeClass('hidden');
        $('#btn-container').removeClass('justify-center').addClass('justify-between');
    }
});

// 초(seconds)를 00:00:00 형식으로 변환하는 함수
function formatTime(totalSeconds) {
    const h = Math.floor(totalSeconds / 3600);
    const m = Math.floor((totalSeconds % 3600) / 60);
    const s = totalSeconds % 60;
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
}

function startSession() {
    sessionStorage.removeItem('pastTime'); // 새 세션이므로 누적 시간 초기화

    $.ajax({
        type: 'POST',
        url: '/timerstart',
        data: {},
        success: function (response) {
            if (response['result'] == 'success') {
                const serverStartTime = response['nowtime'];
                const clientStartTime = Date.now(); // 서버 시간 대신 브라우저 시간 기준 사용
                
                sessionStorage.setItem('serverStartTime', serverStartTime);
                sessionStorage.setItem('clientStartTime', clientStartTime);

                let timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
            <p class="text-3xl font-black text-green-700">${serverStartTime}</p>
            <h2 class="text-m font-bold text-gray-400 tracking-widest mt-1 mb-1">지금까지 이만큼 공부했어요</h2>
            <p id="stopwatch-display" class="text-3xl font-black text-green-700">00:00:00</p>`;

                $('#start-time-display').html(timehtml);
                $('#start-btn').addClass('hidden');
                $('#pause-btn').removeClass('hidden').text('휴식');
                $('#end-btn').removeClass('hidden');
                $('#btn-container').removeClass('justify-center').addClass('justify-between');

                startStopwatch(clientStartTime, 0);
            } else {
                alert(response['message']);
            }
        },
        error: function (err) {
            alert("타이머 시작에 실패했습니다. 로그인을 다시 확인해주세요.");
        }
    });
}

let timeInterval;

function startStopwatch(clientStartTime, pastTime = 0) {
    if (timeInterval) clearInterval(timeInterval);

    timeInterval = setInterval(function () {
        const now = Date.now();
        const diff = now - parseInt(clientStartTime);

        const totalSeconds = Math.floor(diff / 1000) + parseInt(pastTime);
        $('#stopwatch-display').text(formatTime(totalSeconds));
    }, 1000);
}

function pauseSession() {
    if ($('#pause-btn').text() == '휴식') {
        $.ajax({
            type: 'POST',
            url: '/timerend',
            data: {},
            success: function (response) {
                if (response['result'] == 'success') {
                    // 서버 승인이 나면 그제서야 타이머를 멈춥니다! (고장나는 화면 방지)
                    clearInterval(timeInterval);
                    
                    const sessionSeconds = response['this_session_seconds'];
                    let currentPast = parseInt(sessionStorage.getItem('pastTime')) || 0;
                    const newPast = currentPast + sessionSeconds;
                    sessionStorage.setItem('pastTime', newPast);

                    sessionStorage.removeItem('clientStartTime');
                    sessionStorage.removeItem('serverStartTime');

                    $('#pause-btn').text('재개');
                    $('#pause-btn')
                        .removeClass('border-green-300 bg-green-500/80 hover:bg-red-500/30')
                        .addClass('border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30');
                    
                    $('#stopwatch-display').text(formatTime(newPast));
                    $('#start-time-display p:first').text('휴식 중').removeClass('text-green-700').addClass('text-gray-400');
                } else {
                    alert(response['message'] || '잠시 후 다시 시도해주세요!');
                }
            }
        });
    } else {
        // 재개 요청
        $.ajax({
            type: 'POST',
            url: '/timerstart',
            data: {},
            success: function (response) {
                if (response['result'] == 'success') {
                    const newServerStartTime = response['nowtime'];
                    const newClientStartTime = Date.now();
                    const accumulated = parseInt(sessionStorage.getItem('pastTime')) || 0;

                    sessionStorage.setItem('serverStartTime', newServerStartTime);
                    sessionStorage.setItem('clientStartTime', newClientStartTime);

                    $('#pause-btn').text('휴식');
                    $('#pause-btn')
                        .removeClass('border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30')
                        .addClass('border-green-300 bg-green-500/80 hover:bg-red-500/30');
                    
                    $('#start-time-display p:first').text(newServerStartTime).removeClass('text-gray-400').addClass('text-green-700');

                    startStopwatch(newClientStartTime, accumulated);
                } else {
                    alert(response['message']);
                }
            }
        });
    }
}

function endSession() {
    if (!confirm('정말 종료 하시겠습니까?')) return;

    // 완전히 종료할 때는 브라우저에 저장된 임시 데이터를 모두 깔끔하게 날립니다.
    sessionStorage.removeItem('clientStartTime');
    sessionStorage.removeItem('serverStartTime');
    sessionStorage.removeItem('pastTime');

    if ($('#pause-btn').text() == '재개') {
        alert('수고하셨습니다! 결과 페이지로 이동합니다.');
        window.location.href = '/result';
    } else {
        window.location.href = '/result';
    }
}
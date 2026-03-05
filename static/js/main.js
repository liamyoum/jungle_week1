$(document).ready(function () {
	const savedStartTime = sessionStorage.getItem('startTime');
	if (savedStartTime) {
		const accumulated = sessionStorage.getItem('pastTime') || 0;

		// 새로고침해도 스탑워치 UI가 유지되도록 HTML 삽입
		let timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
              <p class="text-3xl font-black text-green-700">${savedStartTime}</p>
              <h2 class="text-m font-bold text-gray-400 tracking-widest mt-1 mb-1">지금까지 이만큼 공부했어요</h2>
              <p id="stopwatch-display" class="text-3xl font-black text-green-700">00:00:00</p>`;

		$('#start-time-display').html(timehtml);

		$('#start-btn').addClass('hidden');
		$('#pause-btn').removeClass('hidden');
		$('#end-btn').removeClass('hidden');
		$('#btn-container')
			.removeClass('justify-center')
			.addClass('justify-between');

		startStopwatch(savedStartTime, accumulated);
	}
});

function startSession() {
	// 새 세션을 시작할 때는 이전 과거 누적 시간을 초기화합니다.
	sessionStorage.removeItem('pastTime');

	$.ajax({
		type: 'POST',
		url: '/timerstart',
		data: {},
		success: function (response) {
			if (response['result'] == 'success') {
				const serverStartTime = response['nowtime'];
				sessionStorage.setItem('startTime', serverStartTime);

				let timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
              <p class="text-3xl font-black text-green-700">${serverStartTime}</p>
              <h2 class="text-m font-bold text-gray-400 tracking-widest mt-1 mb-1">지금까지 이만큼 공부했어요</h2>
              <p id="stopwatch-display" class="text-3xl font-black text-green-700">00:00:00</p>`;

				$('#start-time-display').html(timehtml);

				$('#start-btn').addClass('hidden');
				$('#pause-btn').removeClass('hidden');
				$('#end-btn').removeClass('hidden');

				$('#btn-container')
					.removeClass('justify-center')
					.addClass('justify-between');

				startStopwatch(serverStartTime);
			} else {
                alert(response['message']);
            }
		},
		error: function (err) {
            console.log(err);
            alert("타이머 시작에 실패했습니다. 로그인을 다시 확인해주세요.");
        }
	});
}

let timeInterval;
let totalSeconds = 0;

function startStopwatch(startTimeStr, pastTime = 0) {
	const t = startTimeStr.split(':'); 
	const startTime = new Date(t[0], t[1] - 1, t[2], t[3], t[4], t[5]);

	if (timeInterval) clearInterval(timeInterval);

	timeInterval = setInterval(function () {
		const now = new Date();
		const diff = now - startTime;

		totalSeconds = Math.floor(diff / 1000) + parseInt(pastTime);

		const h = Math.floor(totalSeconds / 3600);
		const m = Math.floor((totalSeconds % 3600) / 60);
		const s = totalSeconds % 60;

		const displayTime =
			String(h).padStart(2, '0') +
			':' +
			String(m).padStart(2, '0') +
			':' +
			String(s).padStart(2, '0');

		$('#stopwatch-display').text(displayTime);
	}, 1000);
}

function pauseSession() {
	if ($('#pause-btn').text() == '휴식') {
		clearInterval(timeInterval);

		$.ajax({
			type: 'POST',
			url: '/timerend',
			data: {},
			success: function (response) {
				console.log('서버 응답:', response); 

				if (response['result'] == 'success') {
					// 변경됨: 서버에서 제공하는 정확한 이번 세션 시간(초)을 사용
					const sessionSeconds = response['this_session_seconds'];

					let currentPast = parseInt(sessionStorage.getItem('pastTime')) || 0;
					sessionStorage.setItem('pastTime', currentPast + sessionSeconds);

					$('#pause-btn').text('재개');
					$('#pause-btn')
						.removeClass('border-green-300 bg-green-500/80 hover:bg-red-500/30')
						.addClass('border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30');
                        
					sessionStorage.removeItem('startTime'); 
				} else {
					alert(response['message'] || '잠시 후 다시 시도해주세요!');
				}
			}
		});
	} else {
		// 재개 버튼 누를 때
		$.ajax({
			type: 'POST',
			url: '/timerstart',
			data: {},
			success: function (response) {
				if (response['result'] == 'success') {
					const newStartTime = response['nowtime'];
					const accumulated = sessionStorage.getItem('pastTime') || 0;

					$('#pause-btn').text('휴식');
					$('#pause-btn')
						.removeClass('border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30')
						.addClass('border-green-300 bg-green-500/80 hover:bg-red-500/30');
                        
					sessionStorage.setItem('startTime', newStartTime);
					startStopwatch(newStartTime, accumulated);
				} else {
					alert(response['message']);
				}
			}
		});
	}
}

function endSession() {
	if (!confirm('정말 종료 하시겠습니까?')) return;

	if ($('#pause-btn').text() == '재개') {
		sessionStorage.removeItem('startTime');
        sessionStorage.removeItem('pastTime');
		alert('수고하셨습니다! 결과 페이지로 이동합니다.');
		window.location.href = '/result';
	} else {
        sessionStorage.removeItem('startTime');
        sessionStorage.removeItem('pastTime');
		window.location.href = '/result';
	}
}
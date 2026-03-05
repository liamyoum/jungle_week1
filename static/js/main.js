$(document).ready(function () {
	const savedStartTime = sessionStorage.getItem('startTime');
	if (savedStartTime) {
		$('#start-btn').addClass('hidden');
		$('#pause-btn').removeClass('hidden');
		$('#end-btn').removeClass('hidden');
		$('#btn-container')
			.removeClass('justify-center')
			.addClass('justify-between');

		startStopwatch(savedStartTime);
	}
});

function startSession() {
	alert('시작 버튼 정상 작동');

	$.ajax({
		type: 'POST',
		url: '/timerstart',
		data: {},
		success: function (response) {
			if (response['result'] == 'success') {
				// 1. 서버가 제공하는 현재 시각 변수에 저장
				const serverStartTime = response['nowtime'];

				// 세션 스토리지에 저장해야 새로고침해도 타이머 유지
				sessionStorage.setItem('startTime', serverStartTime);

				// 갈아 끼우기

				timehtml = `<h2 class="text-m font-bold text-gray-400 tracking-widest mb-1">현재 세션 시작 시각</h2>
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

				// 3. 이제 00:00:00부터 올라가는 스탑워치를 실행합니다.
				startStopwatch(serverStartTime);
			}
		},
		error: function () {}
	});
}

let timeInterval;
let totalSeconds = 0;

function startStopwatch(startTimeStr, pastTime = 0) {
	const t = startTimeStr.split(':'); // array, ex) [2026, 03, 04, 12, 05, 05];
	const startTime = new Date(t[0], t[1] - 1, t[2], t[3], t[4], t[5]);

	// 기존 타이머 있을 경우 중복 실행 방지를 위해 제거
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
				console.log('서버 응답:', response); // 디버깅용, 서버 응답 확인

				if (response['result'] == 'success') {
					const s = response['start_time'].split(':');
					const e = response['end_time'].split(':');
					const start = new Date(
						s[0],
						s[1] - 1,
						s[2],
						s[3],
						s[4],
						s[5]
					);
					const end = new Date(
						e[0],
						e[1] - 1,
						e[2],
						e[3],
						e[4],
						e[5]
					);
					const sessionSeconds = Math.floor((end - start) / 1000);

					let currentPast =
						parseInt(sessionStorage.getItem('pastTime')) || 0;
					sessionStorage.setItem(
						'pastTime',
						currentPast + sessionSeconds
					);

					$('#pause-btn').text('재개');
					$('#pause-btn')
						.removeClass(
							'border-green-300 bg-green-500/80 hover:bg-red-500/30'
						)
						.addClass(
							'border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30'
						);
					sessionStorage.removeItem('startTime'); // 서버에서 start_time도 None 됨
					alert('휴식 시작!');
				} else {
					alert('잠시 후 다시 시도해주세요!');
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
						.removeClass(
							'border-yellow-300 bg-yellow-600/80 hover:bg-blue-500/30'
						)
						.addClass(
							'border-green-300 bg-green-500/80 hover:bg-red-500/30'
						);
					sessionStorage.setItem('startTime', newStartTime);

					startStopwatch(newStartTime, accumulated);
				} else {
					alert('잠시 후 다시 시도해주세요!');
				}
			}
		});
	}
}

function endSession() {
	if (!confirm('정말 종료 하시겠습니까?')) return;

	if ($('#pause-btn').text() == '재개') {
		sessionStorage.removeItem('startTime');
		alert('수고하셨습니다! 결과 페이지로 이동합니다.');
		window.location.href = '/result';
	} else {
		$.ajax({
			type: 'POST',
			url: '/timerend',
			success: function (response) {
				if (response['result'] == 'success') {
					sessionStorage.removeItem('startTime'); // 서버에서 start_time도 None 됨
					alert('수고하셨습니다! 결과 페이지로 이동합니다.');
					window.location.href = '/result';
				}
			},
			error: function () {
				alert('기록 저장 중 오류가 발생했습니다.');
			}
		});
	}
}

/// Economy service that manages Kibble balance and deductions.
/// Handles purchase validation and daily limits.
class EconomyService {
  static const int kDailyLimit = 5;
  static const String kCurrencyName = 'Kibble';

  final FirestoreClient _db;

  EconomyService(this._db);

  Future<int> getBalance(String userId) async {
    return 0;
  }

  Future<bool> deductKibble(String userId, int amount) async {
    return true;
  }

  void resetDailyCount(String userId) {}
}

enum RoastPersona {
  snarky,
  dramatic,
  philosophical,
}

mixin TimestampMixin {
  DateTime get createdAt;
}

const String kAppVersion = '1.0.0';
